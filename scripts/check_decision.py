"""Validate a source-backed decision draft without judging its conclusion."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
import search


ROOT = Path(__file__).resolve().parents[1]
NOTICE = "结构通过不代表结论正确"
TEXT_FIELDS = ("author_view", "recommendation", "strongest_alternative", "change_if")
ACTION_FIELDS = ("owner", "deadline", "limit", "artifact", "continue_if", "stop_if")
EVIDENCE_STATUSES = {"source-backed", "insufficient"}
DECISION_SOURCE_TYPES = {"wechat-original", "author-crosspost-summary"}


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _source_error(index: int, message: str) -> str:
    return f"sources[{index}]: {message}"


def _canonical_source(
    reference: Any,
    index: int,
    catalog: dict[str, dict[str, Any]],
    root: Path,
) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    if not isinstance(reference, dict):
        return None, [_source_error(index, "must be an object")]

    source_id = reference.get("source_id")
    if not isinstance(source_id, str) or not source_id.strip():
        errors.append(_source_error(index, "source_id must be a non-empty string"))
        return None, errors
    entry = catalog.get(source_id)
    if entry is None:
        return None, [_source_error(index, f"unknown source_id: {source_id}")]

    raw_source_type = entry.get("source_type")
    source_type = "wechat-original" if raw_source_type is None else raw_source_type
    if not isinstance(source_type, str) or not source_type.strip():
        errors.append(_source_error(index, "catalog source_type must be a string"))
    elif source_type == "author-jianshu-archive-listing":
        errors.append(_source_error(index, "archive listings cannot support a decision"))
    elif source_type not in DECISION_SOURCE_TYPES:
        errors.append(_source_error(index, f"unsupported decision source_type: {source_type}"))

    start = reference.get("start_line")
    end = reference.get("end_line")
    if type(start) is not int or type(end) is not int:
        errors.append(_source_error(index, "start_line and end_line must be integers"))
    elif start < 1 or end < start:
        errors.append(_source_error(index, "invalid line span"))

    title = entry.get("title")
    published_at = entry.get("published_at")
    url = entry.get("url")
    article_path = entry.get("article_path")
    if not _nonempty_string(title):
        errors.append(_source_error(index, "catalog title is missing"))
    if not _nonempty_string(published_at):
        errors.append(_source_error(index, "catalog published_at is missing"))
    if not _nonempty_string(url):
        errors.append(_source_error(index, "catalog url must be non-empty"))
    if not isinstance(article_path, str) or not article_path.strip():
        errors.append(_source_error(index, "catalog article_path is missing"))

    path: Path | None = None
    if isinstance(article_path, str) and article_path.strip():
        relative = Path(article_path)
        if relative.is_absolute() or ".." in relative.parts:
            errors.append(_source_error(index, "article_path escapes the source root"))
        else:
            try:
                path = search.inside_root(article_path, root)
            except (OSError, ValueError, TypeError) as error:
                errors.append(_source_error(index, f"invalid article_path: {error}"))
            else:
                if not path.is_file():
                    errors.append(_source_error(index, "article_path is not a file"))

    if errors or path is None:
        return None, errors

    try:
        raw = path.read_bytes()
        line_count = len(raw.decode("utf-8").splitlines())
    except (OSError, UnicodeDecodeError) as error:
        return None, [_source_error(index, f"cannot read article: {error}")]
    if type(start) is not int or type(end) is not int or end > line_count:
        return None, [_source_error(index, f"line span exceeds article lines ({line_count})")]

    return {
        "source_id": source_id,
        "title": title,
        "published_at": published_at,
        "author": entry.get("author"),
        "url": url,
        "article_path": relative.as_posix(),
        "source_type": source_type,
        "start_line": start,
        "end_line": end,
        "sha256": hashlib.sha256(raw).hexdigest(),
    }, []


def check_decision(record: Any, root: Path = ROOT) -> dict[str, Any]:
    """Check the decision draft's structure and canonicalize its source spans."""
    result: dict[str, Any] = {
        "valid": False,
        "errors": [],
        "sources": [],
        "action": {},
        "notice": NOTICE,
        "evidence_status": None,
        "author_view": None,
        "recommendation": None,
        "strongest_alternative": None,
        "change_if": None,
    }
    errors: list[str] = result["errors"]
    if not isinstance(record, dict):
        errors.append("decision draft must be a JSON object")
        return result

    for field in ("evidence_status",) + TEXT_FIELDS:
        result[field] = record.get(field)

    action = record.get("action")
    if isinstance(action, dict):
        result["action"] = action
    else:
        errors.append("action must be an object")
        action = {}

    status = record.get("evidence_status")
    if not isinstance(status, str) or status not in EVIDENCE_STATUSES:
        errors.append("evidence_status must be 'source-backed' or 'insufficient'")
    for field in TEXT_FIELDS:
        if not _nonempty_string(record.get(field)):
            errors.append(f"{field} must be a non-empty string")
    for field in ACTION_FIELDS:
        if not _nonempty_string(action.get(field)):
            errors.append(f"action.{field} must be a non-empty string")

    references = record.get("sources")
    if not isinstance(references, list):
        errors.append("sources must be a list")
        references = []
    if status == "source-backed" and not references:
        errors.append("source-backed decisions require at least one source")

    try:
        catalog_rows = search.load_catalog(True, True, root=Path(root))
        catalog: dict[str, dict[str, Any]] = {}
        for entry in catalog_rows:
            source_id = entry.get("id") if isinstance(entry, dict) else None
            if isinstance(source_id, str):
                catalog[source_id] = entry
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        errors.append(f"cannot load source catalog: {error}")
        catalog = {}

    for index, reference in enumerate(references):
        canonical, source_errors = _canonical_source(reference, index, catalog, Path(root))
        errors.extend(source_errors)
        if canonical is not None:
            result["sources"].append(canonical)

    result["valid"] = not errors
    return result


def _error_result(message: str) -> dict[str, Any]:
    return {
        "valid": False,
        "errors": [message],
        "sources": [],
        "action": {},
        "notice": NOTICE,
        "evidence_status": None,
        "author_view": None,
        "recommendation": None,
        "strongest_alternative": None,
        "change_if": None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="read the JSON draft from this file")
    args = parser.parse_args(argv)
    try:
        raw = args.input.read_text(encoding="utf-8") if args.input else sys.stdin.read()
        record = json.loads(raw)
    except (OSError, UnicodeDecodeError) as error:
        result = _error_result(f"cannot read input JSON: {error}")
    except json.JSONDecodeError as error:
        result = _error_result(f"invalid JSON: {error.msg}")
    else:
        result = check_decision(record)
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8", errors="strict")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="strict")
    raise SystemExit(main())
