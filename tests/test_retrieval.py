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
        for entry in self.catalog:
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
