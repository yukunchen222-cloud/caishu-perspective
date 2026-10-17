"""Build an allowlisted, source-isolated evaluation bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from datetime import date
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit

sys.dont_write_bytecode = True
try:
    import search
except ModuleNotFoundError:  # pragma: no cover - useful when called by path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import search


SOURCE_TYPES = (
    "wechat-original",
    "author-crosspost-summary",
    "author-jianshu-archive-listing",
)
STATIC_FILES = (
    "SKILL.md",
    "references/methods.md",
    "references/decision-workflow.md",
    "scripts/search.py",
)
OPTIONAL_STATIC_FILES = ("scripts/evidence.py", "scripts/check_decision.py", "references/delivery-check.md")
SOURCE_ID_RE = re.compile(
    r"(?:wxmp-[0-9a-f]{16,40}|crosspost-[0-9a-f]{12}|jianshu-[a-z0-9]{12})"
)


def _json_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative(relative: str | Path) -> Path:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Corpus path outside skill directory")
    return path


def _source_file(root: Path, relative: str | Path) -> Path:
    path = _safe_relative(relative)
    return search.inside_root(path.as_posix(), root)


def _source_type(entry: dict[str, Any]) -> str:
    return entry.get("source_type", "wechat-original")


def _group_map(catalog: list[dict[str, Any]]) -> dict[str, str]:
    """Compatibility fallback for an old copied search module."""
    if hasattr(search, "source_groups"):
        return search.source_groups(catalog)

    parents = {entry["id"]: entry["id"] for entry in catalog}

    def find(item: str) -> str:
        while parents[item] != item:
            parents[item] = parents[parents[item]]
            item = parents[item]
        return item

    def normalized(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip().casefold()

    owners: dict[tuple[str, str], str] = {}
    for entry in catalog:
        keys: list[tuple[str, str]] = []
        title = normalized(entry.get("title", ""))
        if title:
            keys.append(("title", title))
        body = normalized(entry.get("search_text", ""))
        if body:
            keys.append(("body", hashlib.sha256(body.encode("utf-8")).hexdigest()))
        for key in keys:
            if key not in owners:
                owners[key] = entry["id"]
                continue
            left, right = find(entry["id"]), find(owners[key])
            if left != right:
                parents[max(left, right)] = min(left, right)
    return {entry["id"]: find(entry["id"]) for entry in catalog}


def _fallback_select_catalog(
    catalog: list[dict[str, Any]], as_of: str, exclude_ids: Iterable[str]
) -> list[dict[str, Any]]:
    excluded = set(exclude_ids)
    known = {entry["id"] for entry in catalog}
    unknown = excluded - known
    if unknown:
        raise ValueError("Unknown excluded source ID: " + ", ".join(sorted(unknown)))
    cutoff = date.fromisoformat(as_of)
    groups = _group_map(catalog)
    excluded_groups = {groups[source_id] for source_id in excluded}
    selected: list[dict[str, Any]] = []
    for entry in catalog:
        if _source_type(entry) not in set(SOURCE_TYPES):
            continue
        published = entry.get("published_at")
        if not published or date.fromisoformat(published[:10]) > cutoff:
            continue
        if groups[entry["id"]] in excluded_groups:
            continue
        selected.append(entry)
    return selected


def _select_visible(
    catalog: list[dict[str, Any]], case: dict[str, Any]
) -> list[dict[str, Any]]:
    as_of = case.get("as_of")
    if not isinstance(as_of, str):
        raise ValueError("case.as_of must be an ISO date")
    date.fromisoformat(as_of)
    excluded = case.get("held_out_source_ids", [])
    if not isinstance(excluded, list) or not all(isinstance(item, str) for item in excluded):
        raise ValueError("case.held_out_source_ids must be a list of source IDs")
    selector = getattr(search, "select_catalog", None)
    if selector is not None:
        return selector(catalog, scope="all", as_of=as_of, exclude_ids=excluded)
    return _fallback_select_catalog(catalog, as_of, excluded)


def _contains_blocked(line: str, blocked_ids: set[str]) -> bool:
    return any(source_id in line for source_id in blocked_ids)


def _sanitize_methods(text: str, blocked_ids: set[str]) -> tuple[str, list[str]]:
    """Remove complete level-2 baseline sections that depend on hidden IDs."""
    lines = text.splitlines()
    sections: list[list[str]] = []
    preamble: list[str] = []
    current: list[str] | None = None
    for line in lines:
        if line.startswith("## "):
            if current is not None:
                sections.append(current)
            current = [line]
        elif current is None:
            preamble.append(line)
        else:
            current.append(line)
    if current is not None:
        sections.append(current)

    kept: list[str] = [line for line in preamble if not _contains_blocked(line, blocked_ids)]
    removed: list[str] = []
    for section in sections:
        if any(_contains_blocked(line, blocked_ids) for line in section):
            removed.append(section[0][3:].strip())
            continue
        kept.extend(section)
    return "\n".join(kept).rstrip() + "\n", removed


def _sanitize_static_text(text: str, blocked_ids: set[str], *, methods: bool = False) -> tuple[str, list[str]]:
    if methods:
        return _sanitize_methods(text, blocked_ids)
    lines = [line for line in text.splitlines() if not _contains_blocked(line, blocked_ids)]
    return "\n".join(lines).rstrip() + "\n", []


def _copy_static_files(source_root: Path, runtime_root: Path, blocked_ids: set[str]) -> list[str]:
    removed_sections: list[str] = []
    for relative in STATIC_FILES + tuple(
        relative for relative in OPTIONAL_STATIC_FILES if (source_root / relative).is_file()
    ):
        source = _source_file(source_root, relative)
        if not source.is_file():
            raise FileNotFoundError(f"Required bundle file not found: {relative}")
        destination = runtime_root / _safe_relative(relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if relative.endswith("references/methods.md") or relative == "SKILL.md":
            cleaned, removed = _sanitize_static_text(
                source.read_text(encoding="utf-8"), blocked_ids, methods=relative.endswith("methods.md")
            )
            destination.write_text(cleaned, encoding="utf-8")
            removed_sections.extend(removed)
        else:
            shutil.copy2(source, destination)
    return removed_sections


def _copy_visible_documents(
    source_root: Path,
    runtime_root: Path,
    visible: list[dict[str, Any]],
    blocked_ids: set[str],
) -> set[str]:
    """Copy visible documents, omitting analysis cards that cite hidden IDs."""
    excluded_analysis: set[str] = set()
    analysis_paths: set[str] = set()
    document_paths: set[str] = set()
    for entry in visible:
        for key in ("article_path", "analysis_path"):
            relative = entry.get(key)
            if not relative:
                continue
            source = _source_file(source_root, relative)
            if not source.is_file():
                raise FileNotFoundError(f"Visible source file not found: {relative}")
            relative = _safe_relative(relative).as_posix()
            document_paths.add(relative)
            if key == "analysis_path":
                analysis_paths.add(relative)

    for relative in analysis_paths:
        source = _source_file(source_root, relative)
        if _contains_blocked(source.read_text(encoding="utf-8"), blocked_ids):
            excluded_analysis.add(relative)

    for relative in sorted(document_paths - excluded_analysis):
        source = _source_file(source_root, relative)
        destination = runtime_root / _safe_relative(relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    return excluded_analysis


def _url_key(url: str) -> tuple[str, str, str]:
    parsed = urlsplit(url)
    return parsed.netloc.casefold(), parsed.path, parsed.query


def _url_owners(catalog: list[dict[str, Any]]) -> dict[tuple[str, str, str], set[str]]:
    owners: dict[tuple[str, str, str], set[str]] = {}
    for entry in catalog:
        urls = [entry.get("url", "")]
        urls.extend(
            match.get("url", "")
            for match in entry.get("jianshu_title_matches", [])
            if isinstance(match, dict)
        )
        for url in urls:
            if isinstance(url, str) and url:
                owners.setdefault(_url_key(url), set()).add(entry["id"])
    return owners


def _sanitize_visible_entries(
    visible: list[dict[str, Any]],
    catalog: list[dict[str, Any]],
    blocked_ids: set[str],
    excluded_analysis: set[str],
) -> list[dict[str, Any]]:
    owners = _url_owners(catalog)
    sanitized: list[dict[str, Any]] = []
    for entry in visible:
        clean = dict(entry)
        matches = entry.get("jianshu_title_matches")
        if isinstance(matches, list):
            kept_matches: list[Any] = []
            for match in matches:
                if not isinstance(match, dict):
                    continue
                serialized = json.dumps(match, ensure_ascii=False)
                if _contains_blocked(serialized, blocked_ids):
                    continue
                url = match.get("url")
                if (
                    isinstance(url, str)
                    and url
                    and owners.get(_url_key(url), set()) & blocked_ids
                ):
                    continue
                kept_matches.append(match)
            clean["jianshu_title_matches"] = kept_matches
        for key in ("article_path", "analysis_path"):
            relative = clean.get(key)
            if isinstance(relative, str) and _safe_relative(relative).as_posix() in excluded_analysis:
                clean[key] = None
        sanitized.append(clean)
    return sanitized


def _write_filtered_catalogs(runtime_root: Path, visible: list[dict[str, Any]]) -> None:
    by_type = {source_type: [] for source_type in SOURCE_TYPES}
    for entry in visible:
        by_type.setdefault(_source_type(entry), []).append(entry)
    filenames = {
        "wechat-original": "catalog.json",
        "author-crosspost-summary": "crosspost_catalog.json",
        "author-jianshu-archive-listing": "jianshu_archive_catalog.json",
    }
    for source_type, filename in filenames.items():
        _json_write(runtime_root / "corpus" / filename, by_type.get(source_type, []))


def _collect_source_dependencies(record: Any) -> set[str]:
    dependencies: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "source_id" and isinstance(child, str):
                    dependencies.add(child)
                else:
                    walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(record)
    return dependencies


def _filter_support(
    source_root: Path,
    runtime_root: Path,
    visible_ids: set[str],
    known_ids: set[str],
    filename: str,
    key: str,
) -> None:
    source = source_root / "corpus" / filename
    if source.is_file():
        data = json.loads(source.read_text(encoding="utf-8"))
        records = data.get(key, [])
        if not isinstance(records, list):
            raise ValueError(f"Invalid {filename}: {key} must be a list")
    else:
        data = {"schema_version": 1, "notice": "过滤后的评测可见支持材料"}
        records = []

    selected: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        dependencies = _collect_source_dependencies(record)
        unknown = dependencies - known_ids
        if unknown:
            raise ValueError("Unknown decision support source: " + ", ".join(sorted(unknown)))
        if dependencies and dependencies <= visible_ids:
            selected.append(record)

    output = {"schema_version": data.get("schema_version", 1),
              "notice": data.get("notice", "过滤后的评测可见支持材料"), key: selected}
    _json_write(runtime_root / "corpus" / filename, output)


def _entry_date(entry: dict[str, Any]) -> str | None:
    published = entry.get("published_at")
    return published[:10] if isinstance(published, str) and published else None


def _write_manifest(runtime_root: Path, visible: list[dict[str, Any]]) -> None:
    source_counts: dict[str, dict[str, Any]] = {}
    for source_type in SOURCE_TYPES:
        entries = [entry for entry in visible if _source_type(entry) == source_type]
        dates = sorted(value for value in (_entry_date(entry) for entry in entries) if value)
        source_counts[source_type] = {
            "count": len(entries),
            "earliest": dates[0] if dates else None,
            "latest": dates[-1] if dates else None,
        }
    manifest = {"schema_version": 1, "source_counts": source_counts}
    # Keep both conventional locations compatible with old and new consumers.
    _json_write(runtime_root / "manifest.json", manifest)
    _json_write(runtime_root / "corpus" / "manifest.json", manifest)


def _link_from(document_dir: str, target: str) -> str:
    return Path(os.path.relpath(target, document_dir)).as_posix()


def _write_topics(runtime_root: Path, visible: list[dict[str, Any]]) -> None:
    ordered = sorted(visible, key=lambda entry: (_entry_date(entry) or "", entry["id"]), reverse=True)
    references_lines = [
        "# 评测可见主题目录",
        "",
        "本目录仅列出当前评测截点和题组隔离后可见的来源。",
        "",
    ]
    index_lines = [
        "# 评测可见语料",
        "",
        "仅列出当前评测包允许读取的来源文件。",
        "",
    ]
    for entry in ordered:
        source_type = _source_type(entry)
        label = {
            "wechat-original": "公众号原文",
            "author-crosspost-summary": "作者交叉发布摘要",
            "author-jianshu-archive-listing": "简书历史目录卡",
        }.get(source_type, source_type)
        date_label = _entry_date(entry) or "日期未知"
        article = entry.get("article_path")
        analysis = entry.get("analysis_path")
        links: list[str] = []
        if article:
            links.append(f"[来源]({_link_from('references', article)})")
        if analysis and analysis != article:
            links.append(f"[分析]({_link_from('references', analysis)})")
        references_lines.append(f"- {date_label} {entry['title']}（{label}） {' · '.join(links)}")

        index_article = _link_from("corpus/topics", article) if article else ""
        index_lines.append(f"- {date_label} [{entry['title']}]({index_article})（{label}）")

    references_path = runtime_root / "references" / "topics.md"
    references_path.parent.mkdir(parents=True, exist_ok=True)
    references_path.write_text("\n".join(references_lines) + "\n", encoding="utf-8")
    (runtime_root / "corpus/topics/INDEX.md").parent.mkdir(parents=True, exist_ok=True)
    (runtime_root / "corpus/topics/INDEX.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8")


def _write_eval_readme(runtime_root: Path) -> None:
    """Keep the production SKILL link valid without importing the source eval set."""
    path = runtime_root / "evals" / "README.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# 评测隔离包说明\n\n"
        "本包不含评测题目、评分答案或完整题单。评估器只能读取本包的 `runtime/` "
        "和 `request.json`，不得从源库、工作区或网络补读。\n",
        encoding="utf-8",
    )


def _runtime_hashes(runtime_root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(runtime_root.rglob("*")):
        if path.is_file():
            result[path.relative_to(runtime_root.parent).as_posix()] = _sha256(path)
    return result


def _validate_paths(source_root: Path, output: Path) -> tuple[Path, Path]:
    source_root = source_root.expanduser().resolve()
    output = output.expanduser().resolve()
    if not source_root.is_dir():
        raise FileNotFoundError(f"Source root not found: {source_root}")
    if os.path.lexists(output):
        raise FileExistsError(f"Output already exists: {output}")
    if output == source_root or output.is_relative_to(source_root):
        raise ValueError("Output must be outside source_root")
    return source_root, output


def prepare_bundle(source_root: Path, output: Path, case: dict[str, Any], variant: str = "optimized") -> Path:
    """Export a fresh evaluation bundle containing only allowlisted evidence."""
    source_root, output = _validate_paths(Path(source_root), Path(output))
    if not isinstance(case, dict):
        raise ValueError("case must be an object")
    if not isinstance(variant, str) or not variant:
        raise ValueError("variant must be a non-empty string")

    catalog = search.load_catalog(True, True, root=source_root)
    visible = _select_visible(catalog, case)
    visible_ids = {entry["id"] for entry in visible}
    known_ids = {entry["id"] for entry in catalog}
    all_ids = set(known_ids)
    excluded_case_ids = list(case.get("held_out_source_ids", []))
    blocked_ids = all_ids - visible_ids

    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        output.mkdir(exist_ok=False)
    except FileExistsError as error:
        raise FileExistsError(f"Output already exists: {output}") from error

    owned_output = True
    try:
        runtime_root = output / "runtime"
        runtime_root.mkdir(parents=True, exist_ok=True)
        removed_sections = _copy_static_files(source_root, runtime_root, blocked_ids)
        excluded_analysis = _copy_visible_documents(source_root, runtime_root, visible, blocked_ids)
        visible = _sanitize_visible_entries(visible, catalog, blocked_ids, excluded_analysis)
        _write_filtered_catalogs(runtime_root, visible)
        _filter_support(source_root, runtime_root, visible_ids, known_ids, "decision_cases.json", "cases")
        _filter_support(source_root, runtime_root, visible_ids, known_ids, "decision_principles.json", "principles")
        _write_topics(runtime_root, visible)
        _write_eval_readme(runtime_root)
        _write_manifest(runtime_root, visible)

        request = {"prompt": case.get("prompt", ""), "as_of": case["as_of"]}
        _json_write(output / "request.json", request)

        hashes = _runtime_hashes(runtime_root)
        sanitized_baseline = variant == "baseline"
        baseline = {
            "sanitized_baseline": sanitized_baseline,
            "path": "runtime/references/methods.md",
            "removed_sections": removed_sections,
        }
        visible_list = [entry["id"] for entry in visible]
        receipt = {
            "schema_version": 1,
            "variant": variant,
            "excluded_ids": excluded_case_ids,
            "visible_ids": visible_list,
            "not_visible_source_ids": sorted(blocked_ids),
            "files": [{"path": path, "sha256": digest} for path, digest in hashes.items()],
            "file_sha256": hashes,
            "sanitized_baseline": sanitized_baseline,
            "baseline": baseline,
        }
        if excluded_analysis:
            receipt["excluded_analysis_cards"] = sorted(excluded_analysis)
        _json_write(output / "receipt.json", receipt)
    except Exception:
        if owned_output and output.is_dir() and not output.is_symlink():
            shutil.rmtree(output, ignore_errors=True)
        raise
    return output


def _load_case(suite: Path, case_id: str) -> dict[str, Any]:
    data = json.loads(suite.read_text(encoding="utf-8"))
    cases = data.get("cases") if isinstance(data, dict) else None
    if not isinstance(cases, list):
        raise ValueError("Evaluation suite must contain a cases list")
    for case in cases:
        if isinstance(case, dict) and case.get("id") == case_id:
            return case
    raise ValueError("Unknown evaluation case ID: " + case_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--suite", required=True, type=Path)
    parser.add_argument("--variant", default="optimized")
    args = parser.parse_args(argv)
    try:
        case = _load_case(args.suite, args.case_id)
        prepare_bundle(args.source_root, args.output, case, args.variant)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
