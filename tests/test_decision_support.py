"""Decision evidence behavior, including source tiers and held-out data."""
import json
import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import search


class EvidenceRetrievalTests(unittest.TestCase):
    def test_default_search_does_not_present_listing_cards_as_decision_evidence(self):
        listing = json.loads((ROOT / "corpus/jianshu_archive_catalog.json").read_text(encoding="utf-8"))[0]
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/search.py"), listing["title"]],
            capture_output=True, encoding="utf-8", check=True,
        )
        rows = json.loads(result.stdout)["results"]
        self.assertTrue(all(row.get("source_type") != "author-jianshu-archive-listing" for row in rows))

    def test_analysis_only_match_returns_the_original_with_a_labeled_excerpt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "corpus/analysis").mkdir(parents=True)
            (root / "corpus/analysis/example.md").write_text(
                "# 整理者分析\n\n## 作者主张\n可迁移议价能力能增加替代选择。\n", encoding="utf-8"
            )
            entry = {"id": "example", "title": "一个案例", "search_text": "一次经历",
                     "analysis_path": "corpus/analysis/example.md", "article_path": "corpus/articles/example.md"}
            results = search.retrieve("可迁移议价能力", [entry], 5, 350, root=root)
            self.assertEqual([row["id"] for row in results], ["example"])
            self.assertIn("analysis", results[0]["match_fields"])
            self.assertEqual(results[0]["excerpt_kind"], "editor-analysis")
            self.assertIn("整理者分析", results[0]["evidence_notice"])

    def test_hiding_a_source_also_hides_its_linked_repost_and_future_sources(self):
        rows = [
            {"id": "original", "title": "原标题", "published_at": "2024-01-01",
             "search_text": "原文", "url": "https://example.org/original",
             "jianshu_title_matches": [{"url": "https://www.jianshu.com/p/example"}]},
            {"id": "repost", "title": "转载时换标题", "published_at": "2024-02-01",
             "source_type": "author-crosspost-summary", "search_text": "摘要",
             "url": "https://www.jianshu.com/p/example"},
            {"id": "future", "title": "后来的观点", "published_at": "2026-01-01", "search_text": "后来的观点"},
        ]
        visible = search.select_catalog(rows, scope="all", as_of="2025-12-31", exclude_ids=["original"])
        self.assertEqual(visible, [])


class EvidencePackTests(unittest.TestCase):
    def test_published_support_is_traceable_and_separate_from_holdout(self):
        from evidence import load_support, source_reference

        catalog = {entry['id']: entry for entry in search.load_catalog(True, True)}
        support = load_support()
        suite = json.loads((ROOT / 'evals/decisions.json').read_text(encoding='utf-8'))['cases']
        hidden = {source_id for case in suite for source_id in case['held_out_source_ids']}
        self.assertEqual(len(support['cases']), 12)
        self.assertEqual(len(support['principles']), 8)
        manifest = json.loads((ROOT / 'corpus/manifest.json').read_text(encoding='utf-8'))['decision_support']
        self.assertEqual((manifest['case_count'], manifest['principle_count']), (12, 8))
        for item in manifest['files']:
            self.assertEqual(hashlib.sha256((ROOT / item['path']).read_bytes()).hexdigest(), item['sha256'])
        for records in support.values():
            self.assertEqual(len(records), len({row['id'] for row in records}))
            for row in records:
                for ref in row['source_refs']:
                    entry = catalog[ref['source_id']]
                    self.assertNotIn(entry['id'], hidden)
                    self.assertLess(entry['published_at'][:10], '2026-01-01')
                    self.assertEqual(entry['author'], '蔡垒磊')
                    actual = source_reference(ref, catalog, max_chars=20000)
                    raw = (ROOT / entry['article_path']).read_bytes()
                    self.assertEqual(actual['sha256'], hashlib.sha256(raw).hexdigest())
                    self.assertFalse(actual['truncated'])
                    self.assertFalse(actual['full_document_read'])
                if 'outcome_status' in row:
                    self.assertEqual(row['outcome_status'], 'not-observed')
        kinds = {kind: sum(case['kind'] == kind for case in suite)
                 for kind in ('author_holdout', 'counterfactual', 'evidence_boundary')}
        self.assertEqual(kinds, {'author_holdout': 8, 'counterfactual': 16, 'evidence_boundary': 8})
        for case in suite:
            for ref in case['gold']['source_refs']:
                source_reference(ref, catalog, max_chars=20000)
            if case['kind'] == 'counterfactual':
                self.assertTrue(case['gold']['author_direction'].startswith('本次应用判据（非作者原话）'))

    def test_unknown_exclusion_and_invalid_source_span_fail_closed(self):
        from evidence import source_reference

        catalog = search.load_catalog()
        with self.assertRaises(ValueError):
            search.select_catalog(catalog, exclude_ids=['unknown'])
        with self.assertRaises(ValueError):
            source_reference({'source_id': catalog[0]['id'], 'start_line': 1, 'end_line': 99999},
                             {entry['id']: entry for entry in catalog})

    def test_hidden_answer_is_not_exposed_via_a_derived_principle(self):
        from evidence import get_evidence

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "corpus/articles").mkdir(parents=True)
            catalog = []
            for source_id, text in [("visible", "裁员后先看现金流"), ("hidden", "裁员答案SECRET_ANSWER")]:
                path = f"corpus/articles/{source_id}.md"
                (root / path).write_text(text + "\n", encoding="utf-8")
                catalog.append({"id": source_id, "title": text, "published_at": "2024-01-01", "author": "蔡垒磊",
                                "url": f"https://example.org/{source_id}", "article_path": path, "search_text": text})
            for filename, data in [("catalog.json", catalog), ("crosspost_catalog.json", []), ("jianshu_archive_catalog.json", [])]:
                (root / "corpus" / filename).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            (root / "corpus/decision_cases.json").write_text(json.dumps({"cases": []}), encoding="utf-8")
            principle = {"id": "derived", "name": "裁员SECRET_ANSWER", "claim": "隐藏答案的归纳",
                         "source_refs": [{"source_id": "hidden", "start_line": 1, "end_line": 1, "role": "support"}]}
            (root / "corpus/decision_principles.json").write_text(json.dumps({"principles": [principle]}), encoding="utf-8")
            result = get_evidence("裁员", root=root, exclude_ids=["hidden"])
            serialized = json.dumps(result, ensure_ascii=False)
            self.assertNotIn("SECRET_ANSWER", serialized)
            self.assertEqual(result["principles"], [])
            self.assertEqual([row["id"] for row in result["originals"]], ["visible"])


if __name__ == "__main__":
    unittest.main()
