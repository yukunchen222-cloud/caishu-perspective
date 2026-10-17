"""Observable retrieval and portability checks against the distributed corpus."""
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("caishu_search", ROOT / "scripts/search.py")
search = importlib.util.module_from_spec(spec)
spec.loader.exec_module(search)


class CorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = search.load_catalog()
        cls.all_catalog = search.load_catalog(include_crossposts=True, include_archive=True)
        cls.manifest = json.loads((ROOT / "corpus/manifest.json").read_text(encoding="utf-8"))

    def test_full_corpus_integrity_and_pairing(self):
        article_ids = {p.stem for p in (ROOT / "corpus/articles").glob("*.md")}
        analysis_ids = {p.stem for p in (ROOT / "corpus/analysis").glob("*.md")}
        catalog_ids = {e["id"] for e in self.catalog}
        self.assertEqual(len(self.catalog), self.manifest["article_count"])
        self.assertEqual(article_ids, analysis_ids)
        self.assertEqual(article_ids, catalog_ids)
        self.assertEqual(len(article_ids), len(self.manifest["files"]))
        for entry in self.manifest["files"]:
            for kind in ("article", "analysis"):
                path = ROOT / entry[f"{kind}_path"]
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), entry[f"{kind}_sha256"])

    def test_jianshu_archive_reconciliation_and_integrity(self):
        archive = json.loads((ROOT / "corpus/jianshu_archive_catalog.json").read_text(encoding="utf-8"))
        reconciliation = json.loads((ROOT / "corpus/jianshu_history_reconciliation.json").read_text(encoding="utf-8"))
        manifest = self.manifest["author_jianshu_history_reconciliation"]
        self.assertEqual(len(archive), 631)
        self.assertEqual(len(reconciliation["records"]), 1132)
        self.assertEqual(reconciliation["readable_unique_entry_count"], 1132)
        self.assertEqual(reconciliation["exact_title_match_count"], 501)
        self.assertEqual(reconciliation["exact_title_match_wechat_record_count"], 483)
        self.assertEqual(reconciliation["distinct_wechat_originals_matched"], 482)
        self.assertEqual(reconciliation["wechat_originals_without_exact_title_match"], 270)
        self.assertEqual(reconciliation["duplicate_title_mapping_count"], 1)
        self.assertEqual(reconciliation["exact_title_match_crosspost_summary_count"], 18)
        self.assertEqual(reconciliation["title_unmatched_added_count"], 631)
        self.assertEqual(reconciliation["profile_count_gap_unresolved"], 4)
        self.assertEqual(manifest["files"], self.manifest["author_jianshu_history_reconciliation"]["files"])
        self.assertEqual(self.manifest["author_jianshu_archive_count"], 631)
        archive_files = {item["id"]: item for item in manifest["files"]}
        self.assertEqual(set(archive_files), {entry["id"] for entry in archive})
        for entry in archive:
            self.assertEqual(entry["source_type"], "author-jianshu-archive-listing")
            self.assertEqual(urlparse(entry["url"]).hostname, "www.jianshu.com")
            self.assertEqual(hashlib.sha256((ROOT / entry["article_path"]).read_bytes()).hexdigest(), archive_files[entry["id"]]["sha256"])
            card = (ROOT / entry["article_path"]).read_text(encoding="utf-8")
            excerpt = next(line[2:] for line in card.splitlines() if line.startswith("> ") and not line.startswith("> 注："))
            self.assertLessEqual(len(excerpt), 36)
        matched_originals = [entry for entry in self.catalog if entry.get("jianshu_title_matches")]
        self.assertEqual(len(matched_originals), 482)
        self.assertEqual(sum(len(entry["jianshu_title_matches"]) for entry in matched_originals), 483)
        self.assertTrue(all(not source["full_text_verified"] for entry in matched_originals for source in entry["jianshu_title_matches"]))

    def test_archive_retrieval_and_source_boundary(self):
        archive = json.loads((ROOT / "corpus/jianshu_archive_catalog.json").read_text(encoding="utf-8"))
        sample = archive[0]
        results = search.retrieve(sample["title"], self.all_catalog, 5, 350)
        result = next(item for item in results if item["id"] == sample["id"])
        self.assertIn("不含全文", result["evidence_notice"])
        self.assertIn("不是已核验的微信公众号原文", result["evidence_notice"])
        process = subprocess.run([sys.executable, str(ROOT / "scripts/search.py"), "--read", sample["id"], "--start-line", "1", "--end-line", "25"], capture_output=True, encoding="utf-8")
        self.assertEqual(process.returncode, 0, process.stderr)
        output = json.loads(process.stdout)
        self.assertEqual(output["source_type"], "author-jianshu-archive-listing")
        self.assertEqual(output["kind"], "archive_listing")
        self.assertIn("不是人工摘要", output["text"])
        analysis = subprocess.run([sys.executable, str(ROOT / "scripts/search.py"), "--read", sample["id"], "--kind", "analysis"], capture_output=True, encoding="utf-8")
        self.assertNotEqual(analysis.returncode, 0)
        self.assertIn("do not have analysis cards", analysis.stderr)
        matched = next(entry for entry in self.catalog if entry.get("jianshu_title_matches"))
        matched_result = next(item for item in search.retrieve(matched["title"], self.all_catalog, 5, 350) if item["id"] == matched["id"])
        self.assertTrue(matched_result["jianshu_title_matches"])
        self.assertIn("逐篇全文未核验", matched_result["evidence_notice"])

    def test_source_metadata_and_missing_byline_preserved(self):
        for entry in self.catalog:
            self.assertEqual(urlparse(entry["url"]).hostname, "mp.weixin.qq.com")
            self.assertRegex(entry["published_at"], r"^\d{4}-\d{2}-\d{2}T")
            self.assertTrue(entry["title"].strip())
        unsigned = next(e for e in self.catalog if e["id"] == "wxmp-36e75f551bc236d1a941")
        self.assertIsNone(unsigned["author"])

    def test_relative_markdown_links_resolve(self):
        for path in ROOT.rglob("*.md"):
            for link in re.findall(r"\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
                if "://" in link or link.startswith("#"):
                    continue
                target = unquote(link.split("#", 1)[0].strip("<>"))
                if target:
                    self.assertTrue((path.parent / target).is_file(), f"Broken link in {path.relative_to(ROOT)}: {target}")

    def test_exact_title_and_topic_retrieval(self):
        prompts = [
            ("创业成功 最重要的一步", "wxmp-b1f8ef1b75c5e77fce3d"),
            ("销售不是为了成交", "wxmp-581733f2b4d6c77ce483"),
            ("最大的亏损 最确定", "wxmp-36e75f551bc236d1a941"),
            ("家庭 牺牲 事业", "wxmp-1592dd65db930210d3e5"),
            ("养老靠孩子还是靠钱", "wxmp-294d98065331fb312a68"),
        ]
        for query, expected in prompts:
            with self.subTest(query=query):
                results = search.retrieve(query, self.catalog, 5, 350)
                self.assertIn(expected, [r["id"] for r in results])

    def test_no_evidence_for_unrelated_terms(self):
        self.assertEqual(search.retrieve("xyzzynonexistent987q", self.catalog, 5, 350), [])

    def test_cwd_independent_read_and_real_lines(self):
        with tempfile.TemporaryDirectory(prefix="caishu-test-") as temp:
            process = subprocess.run([sys.executable, str(ROOT / "scripts/search.py"), "--read", "wxmp-36e75f551bc236d1a941", "--start-line", "1", "--end-line", "9"], cwd=temp, capture_output=True, encoding="utf-8")
        self.assertEqual(process.returncode, 0, process.stderr)
        output = json.loads(process.stdout)
        self.assertIsNone(output["author"])
        self.assertIn("1: # 你最大的亏损", output["text"])
        self.assertIn("7: 发布时间：2026-06-29", output["text"])
        self.assertFalse(output["truncated"])

    def test_all_catalog_ids_readable_including_short_ids(self):
        for entry in self.all_catalog:
            self.assertIsNotNone(search.ID_PATTERN.fullmatch(entry["id"]), entry["id"])
            self.assertTrue(search.inside_root(entry["article_path"]).is_file())

    def test_path_escape_blocked(self):
        with self.assertRaises(ValueError):
            search.inside_root("../outside.md")
        process = subprocess.run([sys.executable, str(ROOT / "scripts/search.py"), "--read", "../../outside"], capture_output=True, encoding="utf-8")
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("Invalid document ID", process.stderr)

    def test_invalid_line_range_reported(self):
        process = subprocess.run([sys.executable, str(ROOT / "scripts/search.py"), "--read", "wxmp-36e75f551bc236d1a941", "--start-line", "10", "--end-line", "2"], capture_output=True, encoding="utf-8")
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("Invalid line range", process.stderr)

    def test_no_personal_machine_dependency(self):
        for path in list(ROOT.rglob("*.md")) + list(ROOT.rglob("*.py")) + list(ROOT.rglob("*.json")):
            content = path.read_text(encoding="utf-8")
            self.assertIsNone(re.search(r"[A-Za-z]:[\\/]Users[\\/]|127\.0\.0\.1|localhost:\d+", content), str(path.relative_to(ROOT)))


if __name__ == "__main__":
    unittest.main()
