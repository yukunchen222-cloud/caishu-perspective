"""Return source-backed decision cases, conditional principles and reading candidates.

This is a read-only local evidence tool. The host LLM makes the recommendation.
"""
import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

sys.dont_write_bytecode = True
import search

ROOT = Path(__file__).resolve().parents[1]
SUPPORT_FILES = (("corpus/decision_cases.json", "cases"),
                 ("corpus/decision_principles.json", "principles"))


def load_support(root=ROOT):
    result = {}
    for relative, kind in SUPPORT_FILES:
        path = search.inside_root(relative, root)
        result[kind] = json.loads(path.read_text(encoding="utf-8"))[kind] if path.is_file() else []
    return result


def rank_support(query, records, limit):
    query_tokens = set(search.tokens(query))
    ranked = []
    for record in records:
        searchable = " ".join(
            str(record.get(key, "")) for key in (
                "name", "question", "reader_facts", "decision_variables", "claim",
                "author_recommendation", "applies_when", "limits", "not_when", "mechanisms"
            )
        )
        counts = Counter(search.tokens(searchable))
        score = sum(1 + min(counts[token], 3) / 3 for token in query_tokens if counts[token])
        if score:
            ranked.append((score, record))
    return [(record, round(score, 4)) for score, record in sorted(ranked, key=lambda item: (-item[0], item[1]["id"]))[:limit]]


def source_reference(ref, catalog, root=ROOT, max_chars=700):
    entry = catalog[ref["source_id"]]
    if entry.get("source_type", "wechat-original") != "wechat-original":
        raise ValueError("Decision support references must point to original text")
    path = search.inside_root(entry["article_path"], root)
    raw = path.read_bytes()
    lines = raw.decode("utf-8").splitlines()
    start, end = ref["start_line"], ref["end_line"]
    if not isinstance(start, int) or not isinstance(end, int) or not (1 <= start <= end <= len(lines)):
        raise ValueError("Invalid original source span: " + ref["source_id"])
    excerpt = "\n".join(f"{i + 1}: {lines[i]}" for i in range(start - 1, end))
    return {
        **ref, "title": entry["title"], "published_at": entry["published_at"],
        "author": entry.get("author"), "url": entry.get("url", ""),
        "article_path": entry["article_path"], "sha256": hashlib.sha256(raw).hexdigest(),
        "text": excerpt[:max_chars], "truncated": len(excerpt) > max_chars,
        "read_status": "source-spans-read", "full_document_read": False,
    }


def eligible_support(records, known_ids, visible_ids):
    selected = []
    for record in records:
        refs = record.get("source_refs", [])
        if not refs:
            raise ValueError("Decision support record has no source references: " + record["id"])
        dependencies = {ref["source_id"] for ref in refs}
        if not dependencies <= known_ids:
            raise ValueError("Unknown decision support source: " + record["id"])
        if dependencies <= visible_ids:
            selected.append(record)
    return selected


def get_evidence(query, *, root=ROOT, limit=5, as_of=None, exclude_ids=None, include_summaries=True):
    root = Path(root)
    catalog = search.load_catalog(include_crossposts=True, include_archive=True, root=root)
    visible = search.select_catalog(catalog, "evidence" if include_summaries else "originals", as_of, exclude_ids)
    visible_ids = {entry["id"] for entry in visible}
    by_id = {entry["id"]: entry for entry in catalog}
    support = load_support(root)
    selected = {}
    for kind, records in support.items():
        allowed = eligible_support(records, set(by_id), visible_ids)
        selected[kind] = []
        for record, score in rank_support(query, allowed, min(limit, 3)):
            selected[kind].append({
                **record, "retrieval_score": score, "score_kind": "lexical-relevance-not-confidence",
                "record_role": "editor-extraction-not-author-quotation",
                "source_refs": [source_reference(ref, by_id, root) for ref in record["source_refs"]],
            })
    originals = search.retrieve(query, search.select_sources(visible, "originals"), limit, 350, root=root)
    summaries = search.retrieve(query, search.select_sources(visible, "summaries"), min(limit, 3), 350, root=root)
    reading_ids = []
    for kind in ("cases", "principles"):
        for record in selected[kind]:
            for ref in record["source_refs"]:
                if ref["source_id"] not in reading_ids:
                    reading_ids.append(ref["source_id"])
    for record in originals:
        if record["id"] not in reading_ids:
            reading_ids.append(record["id"])
    return {
        "query": query, "as_of": as_of, "state": "reading-candidates-not-a-recommendation",
        "source_policy": "Originals primary; summaries auxiliary; archive listings excluded from decision evidence.",
        "visible_original_count": sum(entry.get("source_type", "wechat-original") == "wechat-original" for entry in visible),
        **selected, "originals": originals, "summaries": summaries,
        "full_text_reading_candidates": reading_ids,
        "notice": "案例/原则是整理者提炼。片段不代表已读全文，先核对所选原文的条件和论证；匹配分不是结论置信度。",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--as-of")
    parser.add_argument("--exclude-id", action="append", default=[])
    parser.add_argument("--originals-only", action="store_true")
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= 10:
        parser.error("--limit must be 1..10")
    try:
        output = get_evidence(args.query, limit=args.limit, as_of=args.as_of,
                              exclude_ids=args.exclude_id, include_summaries=not args.originals_only)
    except (ValueError, KeyError, OSError) as error:
        parser.error(str(error))
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
