"""Fail-closed display entrypoint: validate a JSON draft, then render it once."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
from check_decision import check_decision

ROOT = Path(__file__).resolve().parents[1]


class DeliveryError(ValueError):
    pass


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DeliveryError('JSON包含重复字段，不能确定唯一草稿。')
        result[key] = value
    return result


def decode_draft(raw: str) -> Any:
    return json.loads(raw, object_pairs_hook=_unique_object)


def deliver(record: Any, *, root: Path = ROOT) -> str:
    """Hosts must display only this return value, never the unchecked model stream."""
    checked = check_decision(record, root=root)
    if not checked['valid']:
        raise DeliveryError('草稿未通过结构/来源检查：' + '; '.join(checked['errors']))
    sections = [('作者依据', 'author_view'), ('对你的建议', 'recommendation'),
                ('支持另一选项的最强理由', 'strongest_alternative'), ('改判条件', 'change_if')]
    lines = ['> 结构通过不代表结论正确；以下是辅助决策，不是自动执行授权。', '']
    if checked['evidence_status'] == 'insufficient':
        lines += ['> 原文依据不足，不能据此断言作者会怎样选择。', '']
    for title, key in sections:
        lines += ['## ' + title, '', checked[key].strip(), '']
    lines += ['## 已核对定位的来源', '']
    if not checked['sources']:
        lines += ['无充分原文依据。', '']
    for source in checked['sources']:
        label = source['title'].replace('[', '\\[').replace(']', '\\]')
        lines += [f"- [{label}]({source['url']})｜{source['published_at']}｜{source['source_type']}",
                  f"  本地：{source['article_path']}:{source['start_line']}—{source['end_line']}；导出正文 SHA-256：{source['sha256']}"]
    action = checked['action']
    fields = [('责任人', 'owner'), ('期限', 'deadline'), ('投入上限', 'limit'),
              ('产物', 'artifact'), ('继续条件', 'continue_if'), ('停止条件', 'stop_if')]
    lines += ['', '下一步：' + '／'.join(label + '：' + action[key].strip() for label, key in fields), '']
    return '\n'.join(lines)


def main() -> int:
    try:
        record = decode_draft(sys.stdin.read())
        answer = deliver(record)
    except (ValueError, TypeError, OSError) as error:
        sys.stderr.write('交付被拦截：' + str(error) + '\n')
        return 1
    sys.stdout.write(answer)
    return 0


if __name__ == '__main__':
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='strict')
    raise SystemExit(main())
