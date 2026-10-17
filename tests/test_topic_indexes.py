import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_topic_indexes as topics  # noqa: E402


class TopicIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = topics.load_records(ROOT)
        cls.topic_index_path = ROOT / "corpus/topics/index.json"

    def test_every_unique_catalog_entry_has_one_primary_topic(self):
        ids = [record["id"] for record in self.records]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(self.records), 1401)
        self.assertEqual(
            {key: sum(record["source_type"] == key for record in self.records) for key in {
                "wechat-original", "author-crosspost-summary", "author-jianshu-archive-listing"
            }},
            {
                "wechat-original": 752,
                "author-crosspost-summary": 18,
                "author-jianshu-archive-listing": 631,
            },
        )
        valid_slugs = {topic["slug"] for topic in topics.TOPICS}
        self.assertTrue(all(record["topic_slug"] in valid_slugs for record in self.records))

    def test_uncertain_or_unmatched_entries_are_not_forced_into_a_topic(self):
        weak = topics.score_topics("一件小事", "没有主题证据")
        self.assertEqual(weak, [])
        result = topics.classify_entry(ROOT, {
            "id": "example", "title": "一件小事", "article_path": "corpus/jianshu_archive/example.md",
            "published_at": "2020-01-01", "search_text": "一件小事",
        }, "author-jianshu-archive-listing", "简书历史目录卡")
        self.assertEqual(result["topic_slug"], topics.OTHER_SLUG)
        self.assertEqual(result["confidence"], "待复核")

    def test_specific_title_phrase_breaks_generic_keyword_tie(self):
        result = topics.classify_entry(ROOT, {
            "id": "emotion-value", "title": "什么是情绪价值？", "article_path": "corpus/crossposts/example.md",
            "published_at": "2026-01-01", "search_text": "什么是情绪价值？",
        }, "author-crosspost-summary", "简书交叉发布摘要")
        self.assertEqual(result["topic_slug"], "05-婚恋与家庭关系")

        crypto = topics.classify_entry(ROOT, {
            "id": "pi-coin", "title": "PI币要转正了吗？", "article_path": "corpus/crossposts/example.md",
            "published_at": "2026-01-01", "search_text": "PI币要转正了吗？",
        }, "author-crosspost-summary", "简书交叉发布摘要")
        self.assertEqual(crypto["topic_slug"], "01-财富与投资")

    def test_archive_classification_uses_listing_metadata_not_full_text(self):
        archive_record = next(record for record in self.records if record["source_type"] == "author-jianshu-archive-listing")
        self.assertIn("标题与作者页列表导语", archive_record["classification_basis"])

    def test_generated_topic_index_covers_records_and_hashes(self):
        payload = json.loads(self.topic_index_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["unique_entry_count"], 1401)
        self.assertEqual(len(payload["entries"]), 1401)
        manifest = json.loads((ROOT / "corpus/manifest.json").read_text(encoding="utf-8"))
        listed = manifest["topic_index"]["files"]
        self.assertGreaterEqual(len(listed), 11)
        self.assertFalse(manifest["topic_index"]["canonical_article_paths_moved"])
        self.assertEqual(sum(manifest["topic_index"]["primary_topic_counts"].values()), 1401)
        for file_info in listed:
            path = ROOT / file_info["path"]
            self.assertTrue(path.is_file(), file_info["path"])
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(digest, file_info["sha256"], file_info["path"])

    def test_topic_directory_links_resolve(self):
        for topic in topics.TOPICS:
            path = ROOT / "corpus/topics" / topic["slug"] / "INDEX.md"
            self.assertTrue(path.is_file(), str(path))
            for record in self.records:
                if record["topic_slug"] != topic["slug"]:
                    continue
                self.assertTrue((ROOT / record["source_path"]).is_file(), record["source_path"])
                if record["analysis_path"]:
                    self.assertTrue((ROOT / record["analysis_path"]).is_file(), record["analysis_path"])


if __name__ == "__main__":
    unittest.main()
