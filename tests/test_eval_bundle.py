import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from prepare_eval import prepare_bundle


class EvalBundleTests(unittest.TestCase):
    def test_prepare_bundle_exports_only_visible_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            output = Path(directory) / "bundle"
            (source / "corpus").mkdir(parents=True)
            (source / "references").mkdir()
            (source / "scripts").mkdir()
            (source / "SKILL.md").write_text("skill\n", encoding="utf-8")
            (source / "references/methods.md").write_text("methods\n", encoding="utf-8")
            (source / "references/decision-workflow.md").write_text("workflow\n", encoding="utf-8")
            (source / "scripts/search.py").write_text("def marker(): return 'search'\n", encoding="utf-8")
            catalog = []
            for source_id, published in (("visible", "2024-01-01"), ("hidden", "2024-01-01"), ("future", "2026-01-01")):
                relative = f"corpus/articles/{source_id}.md"
                (source / relative).parent.mkdir(parents=True, exist_ok=True)
                (source / relative).write_text(f"{source_id} body\n", encoding="utf-8")
                catalog.append({"id": source_id, "title": source_id, "published_at": published,
                                "author": "蔡垒磊", "url": f"https://example.org/{source_id}",
                                "article_path": relative, "analysis_path": None,
                                "search_text": f"{source_id} body"})
            for filename, data in (("catalog.json", catalog), ("crosspost_catalog.json", []),
                                   ("jianshu_archive_catalog.json", [])):
                (source / "corpus" / filename).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

            case = {"id": "case", "prompt": "visible", "as_of": "2025-12-31",
                    "held_out_source_ids": ["hidden"]}
            prepare_bundle(source, output, case)
            exported = json.loads((output / "runtime/corpus/catalog.json").read_text(encoding="utf-8"))
            self.assertEqual([entry["id"] for entry in exported], ["visible"])
            self.assertTrue((output / "runtime/corpus/articles/visible.md").is_file())
            self.assertFalse((output / "runtime/corpus/articles/hidden.md").exists())
            self.assertFalse((output / "runtime/corpus/articles/future.md").exists())
            topics = (output / "runtime/references/topics.md").read_text(encoding="utf-8")
            self.assertTrue(topics.startswith("# "))
            self.assertIn("[来源](../corpus/articles/visible.md)", topics)
            self.assertTrue((output / "runtime/evals/README.md").is_file())
            receipt = json.loads((output / "receipt.json").read_text(encoding="utf-8"))
            self.assertFalse(receipt["sanitized_baseline"])

    def test_hidden_ids_are_removed_from_metadata_and_analysis_cards(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            output = Path(directory) / "bundle"
            for relative in ("corpus", "references", "scripts"):
                (source / relative).mkdir(parents=True)
            (source / "SKILL.md").write_text("skill\n", encoding="utf-8")
            (source / "references/methods.md").write_text("methods\n", encoding="utf-8")
            (source / "references/decision-workflow.md").write_text("workflow\n", encoding="utf-8")
            (source / "scripts/search.py").write_text("def marker(): return 'search'\n", encoding="utf-8")

            visible_id = "wxmp-aaaaaaaaaaaaaaaa"
            hidden_id = "wxmp-bbbbbbbbbbbbbbbb"
            future_id = "wxmp-cccccccccccccccc"
            entries = []
            for source_id, title, published in (
                (visible_id, "Visible", "2024-01-01"),
                (hidden_id, "Held out", "2024-02-01"),
                (future_id, "Future", "2026-01-01"),
            ):
                article = f"corpus/articles/{source_id}.md"
                (source / article).parent.mkdir(parents=True, exist_ok=True)
                (source / article).write_text(f"{title} body\n", encoding="utf-8")
                entries.append({
                    "id": source_id,
                    "title": title,
                    "published_at": published,
                    "author": "蔡垒磊",
                    "url": f"https://example.org/{source_id}",
                    "article_path": article,
                    "analysis_path": None,
                    "search_text": f"{title} body",
                })
            analysis = f"corpus/analysis/{visible_id}.md"
            (source / analysis).parent.mkdir(parents=True, exist_ok=True)
            (source / analysis).write_text(
                f"# analysis\n\n这张卡误引了 {hidden_id}。\n", encoding="utf-8"
            )
            entries[0]["analysis_path"] = analysis
            entries[0]["jianshu_title_matches"] = [{
                "title": "future listing",
                "published_at": "2026-01-01",
                "url": f"https://example.org/{future_id}",
            }]
            entries[2]["url"] = f"https://example.org/{future_id}"
            for filename, data in (
                ("catalog.json", entries),
                ("crosspost_catalog.json", []),
                ("jianshu_archive_catalog.json", []),
            ):
                (source / "corpus" / filename).write_text(
                    json.dumps(data, ensure_ascii=False), encoding="utf-8"
                )

            case = {"id": "case", "prompt": "visible", "as_of": "2025-12-31",
                    "held_out_source_ids": [hidden_id]}
            prepare_bundle(source, output, case)
            exported = json.loads((output / "runtime/corpus/catalog.json").read_text(encoding="utf-8"))
            self.assertEqual([entry["id"] for entry in exported], [visible_id])
            self.assertEqual(exported[0]["jianshu_title_matches"], [])
            self.assertIsNone(exported[0]["analysis_path"])
            self.assertFalse((output / "runtime" / analysis).exists())
            runtime_text = "\n".join(
                path.read_text(encoding="utf-8")
                for path in (output / "runtime").rglob("*")
                if path.is_file()
            )
            self.assertNotIn(hidden_id, runtime_text)

    def test_rejects_existing_output_bad_scope_and_unknown_holdout_without_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            (source / "corpus").mkdir(parents=True)
            (source / "references").mkdir()
            (source / "scripts").mkdir()
            for relative, text in (
                ("SKILL.md", "skill\n"),
                ("references/methods.md", "methods\n"),
                ("references/decision-workflow.md", "workflow\n"),
                ("scripts/search.py", "search\n"),
            ):
                (source / relative).write_text(text, encoding="utf-8")
            for filename in ("catalog.json", "crosspost_catalog.json", "jianshu_archive_catalog.json"):
                (source / "corpus" / filename).write_text("[]", encoding="utf-8")
            case = {"as_of": "2025-12-31", "held_out_source_ids": []}

            existing = root / "existing"
            existing.mkdir()
            with self.assertRaises(FileExistsError):
                prepare_bundle(source, existing, case)

            with self.assertRaises(ValueError):
                prepare_bundle(source, source / "inside", case)

            unknown_output = root / "unknown"
            with self.assertRaises(ValueError):
                prepare_bundle(
                    source,
                    unknown_output,
                    {"as_of": "2025-12-31", "held_out_source_ids": ["missing"]},
                )
            self.assertFalse(unknown_output.exists())
            self.assertEqual((source / "SKILL.md").read_text(encoding="utf-8"), "skill\n")

    def test_does_not_require_directory_replace_on_windows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            output = root / "bundle"
            (source / "corpus").mkdir(parents=True)
            (source / "references").mkdir()
            (source / "scripts").mkdir()
            for relative in (
                "SKILL.md",
                "references/methods.md",
                "references/decision-workflow.md",
                "scripts/search.py",
            ):
                (source / relative).write_text(relative, encoding="utf-8")
            for filename in ("catalog.json", "crosspost_catalog.json", "jianshu_archive_catalog.json"):
                (source / "corpus" / filename).write_text("[]", encoding="utf-8")

            with patch.object(Path, "replace", side_effect=PermissionError("directory rename denied")):
                prepare_bundle(source, output, {"as_of": "2025-12-31", "held_out_source_ids": []})
            self.assertTrue((output / "request.json").exists())


if __name__ == "__main__":
    unittest.main()
