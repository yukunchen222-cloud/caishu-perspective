"""Read-only Chinese/English retrieval; Python standard library, no network."""
import argparse
import collections
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ID_PATTERN = re.compile(r"wxmp-[0-9a-f]{16,40}")


def tokens(text):
    text = text.casefold()
    words = re.findall(r"[a-z0-9]+", text)
    for run in re.findall(r"[\u3400-\u9fff]+", text):
        if len(run) == 1:
            words.append(run)
        else:
            words.extend(run[i:i + 2] for i in range(len(run) - 1))
    return words


def load_catalog():
    catalog = json.loads((ROOT / "corpus/catalog.json").read_text(encoding="utf-8"))
    if not isinstance(catalog, list):
        raise ValueError("Invalid corpus catalog")
    return catalog


def inside_root(relative):
    path = (ROOT / relative).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError("Corpus path outside skill directory")
    return path


def retrieve(query, catalog, limit, max_chars):
    query_tokens = set(tokens(query))
    if not query_tokens:
        return []
    documents = []
    frequency = collections.Counter()
    for entry in catalog:
        counter = collections.Counter(tokens(entry["search_text"]))
        documents.append((entry, counter, sum(counter.values())))
        frequency.update(query_tokens & counter.keys())
    average = sum(length for _, _, length in documents) / max(len(documents), 1)
    ranked = []
    for entry, counter, length in documents:
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
        text = entry["search_text"]
        positions = [text.casefold().find(t) for t in query_tokens if text.casefold().find(t) >= 0]
        center = min(positions, default=0)
        excerpt = text[max(0, center - 50):max(0, center - 50) + max_chars]
        result = {k: entry[k] for k in ("id", "title", "published_at", "author", "url", "article_path", "analysis_path")}
        result.update({"score": round(score, 4), "excerpt": excerpt, "evidence_notice": "检索片段仅作导航；引用前读取相关原文，分析卡不等于作者原话"})
        ranked.append(result)
    return sorted(ranked, key=lambda r: (-r["score"], r["id"]))[:limit]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", nargs="?")
    parser.add_argument("--limit", type=int, default=5)
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
    catalog = load_catalog()
    if args.read:
        if not ID_PATTERN.fullmatch(args.read):
            parser.error("Invalid document ID")
        entry = next((e for e in catalog if e["id"] == args.read), None)
        if entry is None:
            parser.error("Document ID not found")
        path = inside_root(entry["article_path" if args.kind == "article" else "analysis_path"])
        lines = path.read_text(encoding="utf-8").splitlines()
        end = min(args.end_line or len(lines), len(lines))
        if args.start_line < 1 or (args.end_line is not None and args.end_line < args.start_line) or args.start_line > len(lines):
            parser.error("Invalid line range")
        selected = "\n".join(f"{i + 1}: {lines[i]}" for i in range(args.start_line - 1, end))
        clipped = len(selected) > args.max_chars
        output = {"id": entry["id"], "title": entry["title"], "published_at": entry["published_at"], "author": entry["author"], "url": entry["url"], "kind": args.kind, "path": str(path.relative_to(ROOT)).replace("\\", "/"), "total_lines": len(lines), "requested_start_line": args.start_line, "requested_end_line": end, "truncated": clipped, "text": selected[:args.max_chars]}
    else:
        output = {"query": args.query, "results": retrieve(args.query, catalog, args.limit, args.max_chars)}
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
