import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))


class AttributionTests(unittest.TestCase):
    def test_retrieved_author_advice_is_separate_from_editor_correction(self):
        from evidence import get_evidence
        pack = get_evidence('辞职 家族生意 持续增量', root=ROOT, limit=3)
        case = next(row for row in pack['cases'] if row['id'] == 'case-family-business-exit')
        self.assertTrue(case.get('editor_notes'))
        for note in case['editor_notes']:
            self.assertNotIn(note, case['author_recommendation'])
        self.assertTrue(case['source_refs'])


def draft():
    return {
        'evidence_status': 'source-backed',
        'author_view': '原文以具体条件解释选择；这是测试草稿，不是完整决策。',
        'recommendation': '测试建议：先核对用户约束。',
        'strongest_alternative': '测试反方：维持现状有其理由。',
        'change_if': '若关键事实变化则重新判断。',
        'sources': [{'source_id': 'wxmp-1592dd65db930210d3e5', 'start_line': 14, 'end_line': 14}],
        'action': {'owner': '读者', 'deadline': '建议2天内', 'limit': '建议最多1小时、不新增资金',
                   'artifact': '一页事实表', 'continue_if': '取得可核验资料', 'stop_if': '无法核验关键条件'},
    }


class DeliveryGatewayTests(unittest.TestCase):
    def test_valid_draft_becomes_complete_display_without_llm_rewriting(self):
        result = subprocess.run(
            [sys.executable, '-X', 'utf8', str(ROOT / 'scripts/decision_gateway.py')],
            input=json.dumps(draft(), ensure_ascii=False), capture_output=True, encoding='utf-8', cwd=ROOT.parent,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('https://mp.weixin.qq.com/s/Jlk_WVmyNOigJH2BTZ5jRA', result.stdout)
        for key in ('author_view', 'recommendation', 'strongest_alternative', 'change_if'):
            self.assertIn(draft()[key], result.stdout)
        for value in draft()['action'].values():
            self.assertIn(value, result.stdout)
        self.assertIn('结构通过不代表结论正确', result.stdout)

    def test_failed_validation_never_displays_private_draft(self):
        record = draft()
        record['recommendation'] = 'PRIVATE_UNCHECKED_DRAFT'
        del record['action']['limit']
        result = subprocess.run(
            [sys.executable, '-X', 'utf8', str(ROOT / 'scripts/decision_gateway.py')],
            input=json.dumps(record), capture_output=True, encoding='utf-8',
        )
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, '')
        self.assertNotIn('PRIVATE_UNCHECKED_DRAFT', result.stderr)

    def test_generated_draft_is_gated_without_showing_raw_model_events(self):
        from run_decision import generate_and_deliver
        events = [
            {'type': 'item.completed', 'item': {'type': 'command_execution', 'aggregated_output': 'PRIVATE_TRACE'}},
            {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': json.dumps(draft())}},
            {'type': 'turn.completed', 'usage': {'input_tokens': 1, 'output_tokens': 1}},
        ]
        command = [sys.executable, '-c', 'import sys;sys.stdin.read();print(' + repr('\n'.join(json.dumps(e) for e in events)) + ')']
        answer = generate_and_deliver('实际测试请求', root=ROOT, command=command, timeout=10)
        self.assertIn(draft()['recommendation'], answer)
        self.assertNotIn('PRIVATE_TRACE', answer)

    def test_failed_or_incomplete_model_turns_never_become_answers(self):
        from run_decision import generate_and_deliver
        message = {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': json.dumps(draft())}}
        bad = draft()
        del bad['action']['limit']
        for events in ([message], [message, {'type': 'turn.failed'}],
                       [{'type': 'item.completed', 'item': {'type': 'agent_message', 'text': json.dumps(bad)}},
                        {'type': 'turn.completed'}]):
            command = [sys.executable, '-c', 'import sys;sys.stdin.read();print(' + repr('\n'.join(json.dumps(e) for e in events)) + ')']
            with self.subTest(events=events[-1]['type']), self.assertRaises(ValueError):
                generate_and_deliver('测试', root=ROOT, command=command, timeout=10)

    def test_duplicate_json_keys_are_ambiguous_and_rejected(self):
        raw = json.dumps(draft())
        raw = raw[:-1] + ', "recommendation": "PRIVATE_DUPLICATE"}'
        result = subprocess.run(
            [sys.executable, '-X', 'utf8', str(ROOT / 'scripts/decision_gateway.py')],
            input=raw, capture_output=True, encoding='utf-8',
        )
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, '')



if __name__ == '__main__':
    unittest.main()
