import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_decision import check_decision


class DecisionGateTests(unittest.TestCase):
    def test_missing_action_limit_is_rejected(self):
        record = {
            "evidence_status": "source-backed",
            "author_view": "作者建议先核对选择条件。",
            "recommendation": "先做一个小范围验证。",
            "strongest_alternative": "保留现状并继续收集信息。",
            "change_if": "如果关键事实变化就重新判断。",
            "action": {
                "owner": "读者",
                "deadline": "待确认",
                "artifact": "一页验证记录",
                "continue_if": "出现可核对反馈",
                "stop_if": "成本超过上限",
            },
            "sources": [],
        }
        result = check_decision(record, root=ROOT)
        self.assertFalse(result["valid"])
        self.assertTrue(any("limit" in error for error in result["errors"]))

    def test_complete_actual_original_source_returns_canonical_metadata(self):
        record = {
            "evidence_status": "source-backed",
            "author_view": "作者建议先核对真实选择。",
            "recommendation": "先做一个小范围验证。",
            "strongest_alternative": "保留现状并继续收集信息。",
            "change_if": "如果资源或目标变化就重新判断。",
            "action": {
                "owner": "读者",
                "deadline": "待确认",
                "limit": "不超过一周",
                "artifact": "一页验证记录",
                "continue_if": "出现可核对反馈",
                "stop_if": "成本超过上限",
            },
            "sources": [{
                "source_id": "wxmp-1592dd65db930210d3e5",
                "start_line": 14,
                "end_line": 14,
            }],
        }
        result = check_decision(record, root=ROOT)
        self.assertTrue(result["valid"], result["errors"])
        self.assertEqual(len(result["sources"]), 1)
        source = result["sources"][0]
        self.assertEqual(source["url"], "https://mp.weixin.qq.com/s/Jlk_WVmyNOigJH2BTZ5jRA")
        self.assertEqual(source["author"], "蔡垒磊")
        self.assertEqual(source["article_path"], "corpus/articles/wxmp-1592dd65db930210d3e5.md")
        self.assertEqual(source["source_type"], "wechat-original")
        self.assertEqual((source["start_line"], source["end_line"]), (14, 14))
        self.assertEqual(len(source["sha256"]), 64)
        self.assertEqual(result["notice"], "结构通过不代表结论正确")

    def test_insufficient_evidence_may_have_no_sources(self):
        record = {
            "evidence_status": "insufficient",
            "author_view": "尚未找到足够原文证据。",
            "recommendation": "先补齐关键事实。",
            "strongest_alternative": "暂缓做出结论。",
            "change_if": "找到原文后重新判断。",
            "action": {
                "owner": "待确认",
                "deadline": "待确认",
                "limit": "待确认",
                "artifact": "待确认",
                "continue_if": "拿到可核对原文",
                "stop_if": "无法取得原文",
            },
            "sources": [],
        }
        result = check_decision(record, root=ROOT)
        self.assertTrue(result["valid"], result["errors"])
        self.assertEqual(result["sources"], [])

    def test_unknown_id_and_archive_listing_are_rejected(self):
        def draft(source):
            return {
                "evidence_status": "source-backed",
                "author_view": "作者观点待核对。",
                "recommendation": "先核对来源。",
                "strongest_alternative": "暂缓行动。",
                "change_if": "来源变化就重判。",
                "action": {
                    "owner": "读者", "deadline": "待确认", "limit": "待确认",
                    "artifact": "核对记录", "continue_if": "来源可读", "stop_if": "来源缺失",
                },
                "sources": [source],
            }

        unknown = check_decision(
            draft({"source_id": "wxmp-00000000000000000000", "start_line": 1, "end_line": 1}),
            root=ROOT,
        )
        self.assertFalse(unknown["valid"])
        self.assertTrue(any("unknown source_id" in error for error in unknown["errors"]))

        archive = check_decision(
            draft({"source_id": "jianshu-56c8f9c9b458", "start_line": 1, "end_line": 1}),
            root=ROOT,
        )
        self.assertFalse(archive["valid"])
        self.assertTrue(any("archive listings" in error for error in archive["errors"]))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "corpus").mkdir()
            row = {
                "id": "wxmp-aaaaaaaaaaaaaaaa",
                "title": "越界来源",
                "published_at": "2024-01-01",
                "url": "https://example.org/outside",
                "article_path": "../outside.md",
            }
            (root / "corpus/catalog.json").write_text(json.dumps([row]), encoding="utf-8")
            for filename in ("crosspost_catalog.json", "jianshu_archive_catalog.json"):
                (root / "corpus" / filename).write_text("[]", encoding="utf-8")
            escaped = check_decision(
                draft({"source_id": row["id"], "start_line": 1, "end_line": 1}), root=root
            )
            self.assertFalse(escaped["valid"])
            self.assertTrue(any("escapes" in error for error in escaped["errors"]))

    def test_boolean_line_numbers_are_rejected(self):
        record = {
            "evidence_status": "source-backed",
            "author_view": "作者观点。",
            "recommendation": "先验证。",
            "strongest_alternative": "暂缓。",
            "change_if": "事实变化时重判。",
            "action": {
                "owner": "读者", "deadline": "待确认", "limit": "待确认",
                "artifact": "记录", "continue_if": "有反馈", "stop_if": "超预算",
            },
            "sources": [{
                "source_id": "wxmp-1592dd65db930210d3e5",
                "start_line": True,
                "end_line": 14,
            }],
        }
        result = check_decision(record, root=ROOT)
        self.assertFalse(result["valid"])
        self.assertTrue(any("must be integers" in error for error in result["errors"]))

    def test_malformed_evidence_status_fails_closed(self):
        result = check_decision({"evidence_status": []}, root=ROOT)
        self.assertFalse(result["valid"])
        self.assertTrue(any("evidence_status" in error for error in result["errors"]))

    def test_malformed_catalog_source_type_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "corpus/articles").mkdir(parents=True)
            (root / "corpus/articles/item.md").write_text("one\n", encoding="utf-8")
            row = {
                "id": "wxmp-aaaaaaaaaaaaaaaa",
                "title": "恶意类型",
                "published_at": "2024-01-01",
                "url": "https://example.org/item",
                "article_path": "corpus/articles/item.md",
                "source_type": [],
            }
            (root / "corpus/catalog.json").write_text(json.dumps([row]), encoding="utf-8")
            for filename in ("crosspost_catalog.json", "jianshu_archive_catalog.json"):
                (root / "corpus" / filename).write_text("[]", encoding="utf-8")
            record = {
                "evidence_status": "source-backed",
                "author_view": "观点。", "recommendation": "建议。",
                "strongest_alternative": "替代。", "change_if": "变化时重判。",
                "action": {
                    "owner": "读者", "deadline": "待确认", "limit": "待确认",
                    "artifact": "记录", "continue_if": "可验证", "stop_if": "不可验证",
                },
                "sources": [{"source_id": row["id"], "start_line": 1, "end_line": 1}],
            }
            result = check_decision(record, root=root)
            self.assertFalse(result["valid"])
            self.assertTrue(any("source_type" in error for error in result["errors"]))

    def test_cli_fails_closed_for_missing_fields_and_returns_valid_record(self):
        script = ROOT / "scripts/check_decision.py"
        missing = subprocess.run(
            [sys.executable, str(script)], input="{}", capture_output=True,
            encoding="utf-8", check=False,
        )
        self.assertEqual(missing.returncode, 1)
        self.assertNotIn("Traceback", missing.stderr)
        self.assertFalse(json.loads(missing.stdout)["valid"])

        record = {
            "evidence_status": "source-backed",
            "author_view": "作者建议先核对真实选择。",
            "recommendation": "先做一个小范围验证。",
            "strongest_alternative": "保留现状并继续收集信息。",
            "change_if": "如果资源或目标变化就重新判断。",
            "action": {
                "owner": "读者", "deadline": "待确认", "limit": "不超过一周",
                "artifact": "一页验证记录", "continue_if": "出现反馈", "stop_if": "成本超限",
            },
            "sources": [{
                "source_id": "wxmp-1592dd65db930210d3e5",
                "start_line": 14,
                "end_line": 14,
            }],
        }
        valid = subprocess.run(
            [sys.executable, str(script)], input=json.dumps(record, ensure_ascii=False),
            capture_output=True, encoding="utf-8", check=False,
        )
        self.assertEqual(valid.returncode, 0)
        payload = json.loads(valid.stdout)
        self.assertTrue(payload["valid"])
        self.assertEqual(payload["recommendation"], record["recommendation"])


if __name__ == "__main__":
    unittest.main()
