"""Read-only Chinese/English retrieval; Python standard library, no network."""
import argparse
import collections
import hashlib
import json
import math
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
ID_PATTERN = re.compile(r"(?:wxmp-[0-9a-f]{16,40}|crosspost-[0-9a-f]{12}|jianshu-[a-z0-9]{12})")
SOURCE_SCOPES = {
    "evidence": {"wechat-original", "author-crosspost-summary"},
    "originals": {"wechat-original"},
    "summaries": {"author-crosspost-summary"},
    "listings": {"author-jianshu-archive-listing"},
    "all": {"wechat-original", "author-crosspost-summary", "author-jianshu-archive-listing"},
}


def tokens(text):
    text = text.casefold()
    words = re.findall(r"[a-z0-9]+", text)
    for run in re.findall(r"[\u3400-\u9fff]+", text):
        if len(run) == 1:
            words.append(run)
        else:
            words.extend(run[i:i + 2] for i in range(len(run) - 1))
    return words


def load_catalog(include_crossposts=False, include_archive=False, *, root=ROOT):
    root = Path(root)
    catalog = json.loads((root / "corpus/catalog.json").read_text(encoding="utf-8"))
    if not isinstance(catalog, list):
        raise ValueError("Invalid corpus catalog")
    if include_crossposts:
        crossposts = json.loads((root / "corpus/crosspost_catalog.json").read_text(encoding="utf-8"))
        if not isinstance(crossposts, list):
            raise ValueError("Invalid author crosspost catalog")
        catalog.extend(crossposts)
    if include_archive:
        archive = json.loads((root / "corpus/jianshu_archive_catalog.json").read_text(encoding="utf-8"))
        if not isinstance(archive, list):
            raise ValueError("Invalid Jianshu archive catalog")
        catalog.extend(archive)
    return catalog


def inside_root(relative, root=ROOT):
    root = Path(root).resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Corpus path outside skill directory")
    return path


def select_sources(catalog, scope="evidence"):
    return [entry for entry in catalog if entry.get("source_type", "wechat-original") in SOURCE_SCOPES[scope]]


def normalized(text):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip().casefold()


def source_groups(catalog):
    """Known same-title/body/URL links, not a claim of semantic deduplication."""
    parents = {entry["id"]: entry["id"] for entry in catalog}
    if len(parents) != len(catalog):
        raise ValueError("Duplicate source IDs")

    def find(item):
        while parents[item] != item:
            parents[item] = parents[parents[item]]
            item = parents[item]
        return item

    owners = {}
    for entry in catalog:
        keys = []
        if normalized(entry.get("title", "")):
            keys.append(("title", normalized(entry["title"])))
        body = normalized(entry.get("search_text", ""))
        if body:
            keys.append(("body", hashlib.sha256(body.encode("utf-8")).hexdigest()))
        urls = [entry.get("url", "")] + [match.get("url", "") for match in entry.get("jianshu_title_matches", [])]
        for url in urls:
            if url:
                parts = urlsplit(url)
                keys.append(("url", (parts.netloc.casefold(), parts.path, parts.query)))
        for key in keys:
            if key in owners:
                first, second = find(entry["id"]), find(owners[key])
                parents[max(first, second)] = min(first, second)
            else:
                owners[key] = entry["id"]
    return {entry["id"]: find(entry["id"]) for entry in catalog}


def select_catalog(catalog, scope="evidence", as_of=None, exclude_ids=None):
    excluded = set(exclude_ids or [])
    known = {entry["id"] for entry in catalog}
    if excluded - known:
        raise ValueError("Unknown excluded source ID: " + ", ".join(sorted(excluded - known)))
    cutoff = date.fromisoformat(as_of) if as_of else None
    groups = source_groups(catalog)
    excluded_groups = {groups[source_id] for source_id in excluded}
    return [entry for entry in select_sources(catalog, scope)
            if groups[entry["id"]] not in excluded_groups
            and (cutoff is None or (entry.get("published_at") and date.fromisoformat(entry["published_at"][:10]) <= cutoff))]


def analysis_text(entry, root=ROOT):
    if entry.get("source_type", "wechat-original") != "wechat-original" or not entry.get("analysis_path"):
        return ""
    path = inside_root(entry["analysis_path"], root)
    if not path.is_file():
        return ""
    selected = []
    active = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            active = line[3:].strip() in {"作者主张", "可复用提炼", "分析与反方检验", "证据边界"}
        elif active:
            selected.append(line)
    return "\n".join(selected)


def retrieve(query, catalog, limit, max_chars, *, root=ROOT):
    query_tokens = set(tokens(query))
    if not query_tokens:
        return []
    documents = []
    frequency = collections.Counter()
    for entry in catalog:
        body = entry["search_text"]
        analysis = analysis_text(entry, root)
        body_tokens = collections.Counter(tokens(body))
        analysis_tokens = collections.Counter(tokens(analysis))
        counter = body_tokens + analysis_tokens
        documents.append((entry, counter, sum(counter.values()), body_tokens, analysis_tokens, analysis))
        frequency.update(query_tokens & counter.keys())
    average = sum(document[2] for document in documents) / max(len(documents), 1)
    ranked = []
    for entry, counter, length, body_tokens, analysis_tokens, analysis in documents:
        score = 0.0
        for token in query_tokens:
            tf = counter[token]
            if tf:
                idf = math.log(1 + (len(documents) - frequency[token] + 0.5) / (frequency[token] + 0.5))
                score += idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * length / max(average, 1)))
        if not score:
            continue
        title_tokens = set(tokens(entry["title"]))
        score += 2 * len(query_tokens & title_tokens)
        if query.casefold() in entry["title"].casefold():
            score += 12
        body_hits = query_tokens & body_tokens.keys()
        analysis_hits = query_tokens & analysis_tokens.keys()
        match_fields = (["body"] if body_hits else []) + (["analysis"] if analysis_hits else [])
        source_type = entry.get("source_type", "wechat-original")
        use_analysis = len(analysis_hits) > len(body_hits)
        text = analysis if use_analysis else entry["search_text"]
        excerpt_kind = "editor-analysis" if use_analysis else {
            "wechat-original": "original-body",
            "author-crosspost-summary": "crosspost-summary",
            "author-jianshu-archive-listing": "archive-listing",
        }[source_type]
        positions = [text.casefold().find(t) for t in query_tokens if text.casefold().find(t) >= 0]
        center = min(positions, default=0)
        excerpt = text[max(0, center - 50):max(0, center - 50) + max_chars]
        result = {k: entry[k] for k in ("id", "title", "published_at", "author", "url", "article_path", "analysis_path") if k in entry}
        result["source_type"] = source_type
        notice = "检索片段仅作导航；引用前读取相关原文，分析卡不等于作者原话"
        if source_type == "author-crosspost-summary":
            notice = "作者简书交叉发布的整理者摘要，不是微信公众号原文；引用时保留来源标签和简书链接"
        elif source_type == "author-jianshu-archive-listing":
            notice = "简书作者页历史目录条目，含列表导语短摘录，不含全文；不是已核验的微信公众号原文，引用请保留简书链接"
        if entry.get("jianshu_title_matches"):
            result["jianshu_title_matches"] = entry["jianshu_title_matches"]
            notice += "；另有简书同标题来源链接，但逐篇全文未核验，引用时区分来源"
        if use_analysis:
            notice += "；当前片段来自整理者分析，不能当作者原话，须回读对应原文"
        result.update({"score": round(score, 4), "score_kind": "lexical-relevance-not-confidence",
                       "match_fields": match_fields, "excerpt_kind": excerpt_kind,
                       "excerpt": excerpt, "evidence_notice": notice, "read_status": "not-yet-read"})
        ranked.append(result)
    return sorted(ranked, key=lambda r: (-r["score"], r["id"]))[:limit]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", nargs="?")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--sources", choices=tuple(SOURCE_SCOPES), default="evidence",
                        help="default: originals and labeled summaries; listings are discovery only")
    parser.add_argument("--as-of", help="only sources published on/before YYYY-MM-DD")
    parser.add_argument("--exclude-id", action="append", default=[], help="hide the entire known source group")
    parser.add_argument("--max-chars", type=int)
    parser.add_argument("--read", metavar="DOCUMENT_ID")
    parser.add_argument("--kind", choices=("article", "analysis"), default="article")
    parser.add_argument("--start-line", type=int, default=1)
    parser.add_argument("--end-line", type=int)
    args = parser.parse_args(argv)
    if args.max_chars is None:
        args.max_chars = 6000 if args.read else 350
    if args.read and args.query:
        parser.error("Choose query or --read, not both")
    if not args.read and not args.query:
        parser.error("Provide query or --read DOCUMENT_ID")
    if not 1 <= args.limit <= 20 or not 80 <= args.max_chars <= 12000:
        parser.error("--limit must be 1..20 and --max-chars 80..12000")
    catalog = load_catalog(include_crossposts=True, include_archive=True)
    try:
        catalog = select_catalog(catalog, "all" if args.read else args.sources, args.as_of, args.exclude_id)
    except ValueError as error:
        parser.error(str(error))
    if args.read:
        if not ID_PATTERN.fullmatch(args.read):
            parser.error("Invalid document ID")
        entry = next((e for e in catalog if e["id"] == args.read), None)
        if entry is None:
            parser.error("Document ID not found")
        if entry.get("source_type") == "author-jianshu-archive-listing":
            if args.kind == "analysis":
                parser.error("Jianshu archive listings do not have analysis cards")
            path_key = "article_path"
            output_kind = "archive_listing"
        else:
            path_key = "article_path" if args.kind == "article" else "analysis_path"
            output_kind = args.kind
        path = inside_root(entry[path_key])
        lines = path.read_text(encoding="utf-8").splitlines()
        end = min(args.end_line or len(lines), len(lines))
        if args.start_line < 1 or (args.end_line is not None and args.end_line < args.start_line) or args.start_line > len(lines):
            parser.error("Invalid line range")
        selected = "\n".join(f"{i + 1}: {lines[i]}" for i in range(args.start_line - 1, end))
        clipped = len(selected) > args.max_chars
        output = {"id": entry["id"], "title": entry["title"], "published_at": entry["published_at"], "author": entry["author"], "url": entry["url"], "kind": output_kind, "source_type": entry.get("source_type", "wechat-original"), "path": str(path.relative_to(ROOT)).replace("\\", "/"), "total_lines": len(lines), "requested_start_line": args.start_line, "requested_end_line": end, "truncated": clipped, "text": selected[:args.max_chars]}
    else:
        output = {"query": args.query, "source_scope": args.sources,
                  "as_of": args.as_of, "results": retrieve(args.query, catalog, args.limit, args.max_chars)}
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
