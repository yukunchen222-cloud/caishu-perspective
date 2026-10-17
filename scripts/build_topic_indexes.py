#!/usr/bin/env python3
"""Build deterministic topic navigation indexes without moving corpus records."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TOPIC_ROOT = Path("corpus/topics")
OTHER_SLUG = "99-综合与待复核"

TOPICS: tuple[dict[str, Any], ...] = (
    {
        "slug": "01-财富与投资",
        "title": "财富与投资",
        "description": "赚钱、资产、投资、房产、消费与养老财务决策。",
        "keywords": (
            "财富自由", "配置资产", "资产配置", "投资标的", "加密货币", "比特币", "定投", "股市", "股票",
            "国债", "上车盘", "投资收益", "股民", "股价", "炒币", "补仓", "短线", "长线", "限购", "回本",
            "机会成本", "通胀", "A股", "币圈", "PI币", "币", "借钱", "开户", "套利", "资产泡沫", "房子",
            "房产", "房地产", "房价", "房贷", "买房", "卖房", "投资", "理财", "资产", "金融",
            "财富", "赚钱", "收入", "现金流", "负债", "债务", "消费", "花钱", "省钱", "省吃俭用",
            "富人", "穷人", "贫富差距", "黄金", "降息", "利率", "美联储", "银行", "保险", "社保",
            "养老金", "养老", "退休金", "楼市", "租售比", "购房", "房东税", "购买力", "抄底", "浮亏",
            "百倍股", "美股", "港股", "加密资产", "代币", "财技", "钱",
        ),
    },
    {
        "slug": "02-创业与商业",
        "title": "创业与商业",
        "description": "创业、生意、企业经营、产品、客户、平台与商业模式。",
        "keywords": (
            "商业模式", "商业化", "创始人", "创业者", "创业", "生意", "商业", "企业", "公司", "老板",
            "经营", "用户", "产品", "营销", "销售", "流量", "平台", "市场", "利润", "项目", "开店",
            "做生意", "管理层", "组织", "合伙", "客户", "品牌", "供应链", "运营", "创业成功", "美团",
            "泡泡玛特", "茅台", "李佳琦", "于东来",
        ),
    },
    {
        "slug": "03-职业与职场",
        "title": "职业与职场",
        "description": "工作、就业、职场关系、劳动、薪酬与职业发展。",
        "keywords": (
            "职业发展", "劳动合同", "打工人", "劳动光荣", "职场", "工作", "职业", "打工", "牛马", "上班",
            "员工", "领导", "同事", "求职", "面试", "跳槽", "辞职", "离职", "裁员", "工资", "薪水",
            "加薪", "升职", "劳动", "雇佣", "就业", "招聘", "劳动力", "职业选择", "职场道理",
            "公务员", "35岁危机", "职场歧视",
        ),
    },
    {
        "slug": "04-学习与成长",
        "title": "学习与成长",
        "description": "学习、阅读、教育、认知、能力、习惯与个人进步。",
        "keywords": (
            "学习能力", "学习速度", "学习方法", "成长速度", "知识付费", "读书", "学习", "阅读", "成长", "进步", "能力",
            "技能", "知识", "认知", "思维", "思考", "教育", "学校", "大学", "考试", "高考", "考研", "考公",
            "研究生", "贫困生", "升学", "学业", "成绩", "培训", "课程", "训练", "努力", "自律", "拖延",
            "专注", "习惯", "老师", "学生", "上进", "复盘", "聪明", "困难", "方法", "实践",
            "改变自己", "道与术", "道比术", "知行合一", "通用能力", "三观", "顶层设计", "高考成绩",
        ),
    },
    {
        "slug": "05-婚恋与家庭关系",
        "title": "婚恋与家庭关系",
        "description": "婚恋、亲密关系、家庭、亲子、代际与日常人际交往。",
        "keywords": (
            "亲密关系", "家庭关系", "人际关系", "维护关系", "维持关系", "情绪价值", "女朋友", "男朋友", "另一半", "婚姻", "婚恋", "恋爱", "结婚", "分手",
            "离婚", "伴侣", "夫妻", "丈夫", "妻子", "老公", "老婆", "男女", "男生", "女生", "女性",
            "男性", "男人", "女人", "女孩", "男孩", "彩礼", "相亲", "爱情", "出轨", "家庭", "父母",
            "孩子", "子女", "生孩子", "育儿", "亲子", "人际", "人际交往", "社交", "单身", "朋友", "人情", "对等", "父亲", "母亲", "PUA",
            "婆媳", "赡养", "靠孩子", "催婚", "催生", "意中人", "不婚", "不生", "婚后", "婚育", "订婚",
        ),
    },
    {
        "slug": "06-人生心理与身心状态",
        "title": "人生、心理与身心状态",
        "description": "人生选择、幸福感、情绪、心态、人性、身心状态与生活意义。",
        "keywords": (
            "幸福感", "人生观", "价值观", "人性", "幸福", "快乐", "痛苦", "焦虑", "内耗", "心理", "情绪",
            "自由", "命运", "人生意义", "选择", "道德", "孤独", "迷茫", "欲望", "自我", "活着",
            "心态", "苦难", "满足", "勇气", "躺平", "精神", "动力", "人生", "痛恨", "压力", "心里",
            "内心", "自私", "人心", "道理", "能量", "精力", "疲惫", "疲劳", "健康", "睡眠",
            "身体", "心情", "吸引力法则", "太累", "身心",
        ),
    },
    {
        "slug": "07-社会与公共议题",
        "title": "社会与公共议题",
        "description": "社会结构、公共政策、制度、国家与公共事件观察。",
        "keywords": (
            "公共政策", "社会保障", "社会问题", "社会现象", "社会结构", "教育公平", "人口老龄化", "国家",
            "中国", "美国", "政府", "政策", "制度", "文明", "人类", "阶层", "公共", "人口", "政治",
            "法治", "民众", "战争", "社会", "国民", "中产", "阶级", "民主", "福利", "人口问题",
            "公共议题", "性侵", "社会规则", "规则", "法律", "校园贷", "网贷", "事件反思", "社会责任",
            "事件", "热点", "案件", "丑闻", "明星", "历史", "文化", "移民", "出国", "润",
        ),
    },
    {
        "slug": "08-科技与行业趋势",
        "title": "科技与行业趋势",
        "description": "AI、科技产品、互联网、技术变化及其行业影响。",
        "keywords": (
            "人工智能", "AI时代", "ChatGPT", "Clawdbot", "AIDOG", "大模型", "自动驾驶", "科技公司", "数字化", "短视频", "互联网",
            "算法", "芯片", "半导体", "机器人", "区块链", "软件", "硬件", "科技", "技术", "行业趋势", "海力士", "三星", "存储芯片",
            "手机", "电商", "游戏", "应用", "更新", "试运营", "产业", "科技发展",
        ),
    },
    {
        "slug": OTHER_SLUG,
        "title": "综合与待复核",
        "description": "标题和可用摘要不足以可靠区分主题，或同时命中多个主题的条目。",
        "keywords": (),
    },
)

TOPIC_BY_SLUG = {topic["slug"]: topic for topic in TOPICS}
TOPICS_BY_SCORE = tuple(topic for topic in TOPICS if topic["slug"] != OTHER_SLUG)

SOURCES = (
    ("corpus/catalog.json", "wechat-original", "公众号原文"),
    ("corpus/crosspost_catalog.json", "author-crosspost-summary", "简书交叉发布摘要"),
    ("corpus/jianshu_archive_catalog.json", "author-jianshu-archive-listing", "简书历史目录卡"),
)


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text).casefold()).strip()


def contains_keyword(text: str, keyword: str) -> bool:
    if keyword.isascii() and len(keyword) <= 3:
        return re.search(rf"(?<![A-Za-z0-9]){re.escape(keyword)}(?![A-Za-z0-9])", text, re.I) is not None
    return keyword.casefold() in text


def extract_analysis_evidence(text: str) -> str:
    sections: list[str] = []
    active = False
    for line in text.splitlines():
        if line.startswith("## "):
            active = line[3:].strip() in {"作者主张", "可复用提炼"}
            continue
        if active:
            sections.append(line)
    return "\n".join(sections)


def evidence_for(root: Path, item: dict[str, Any], source_type: str) -> tuple[str, str]:
    if source_type == "wechat-original":
        analysis_path = root / item["analysis_path"]
        if analysis_path.is_file():
            return extract_analysis_evidence(analysis_path.read_text(encoding="utf-8")), "标题与分析卡作者主张/可复用提炼"
        return "", "仅标题"
    if source_type == "author-crosspost-summary":
        return item.get("search_text", ""), "标题与简书交叉发布摘要"
    return item.get("search_text", ""), "标题与作者页列表导语"


def score_topics(title: str, evidence: str) -> list[dict[str, Any]]:
    title_text = normalize(title)
    evidence_text = normalize(evidence).replace(title_text, " ", 1) if title_text else normalize(evidence)
    scores: list[dict[str, Any]] = []
    for topic in TOPICS_BY_SCORE:
        title_hits = [kw for kw in topic["keywords"] if contains_keyword(title_text, kw)]
        evidence_hits = [kw for kw in topic["keywords"] if contains_keyword(evidence_text, kw)]
        score = 5 * len(title_hits) + len(evidence_hits)
        if score:
            scores.append({
                "slug": topic["slug"],
                "title": topic["title"],
                "score": score,
                "title_hits": title_hits,
                "evidence_hits": evidence_hits,
            })
    return sorted(scores, key=lambda entry: (-entry["score"], entry["slug"]))


def classify_entry(root: Path, item: dict[str, Any], source_type: str, source_label: str) -> dict[str, Any]:
    evidence, basis = evidence_for(root, item, source_type)
    scores = score_topics(item.get("title", ""), evidence)
    if not scores:
        primary = TOPIC_BY_SLUG[OTHER_SLUG]
        confidence = "待复核"
        reason = "没有命中明确主题词"
    else:
        best = scores[0]["score"]
        tied = [score for score in scores if score["score"] == best]
        if len(tied) > 1:
            strongest_title_signal = max(len(score["title_hits"]) for score in tied)
            tied_by_title = [score for score in tied if len(score["title_hits"]) == strongest_title_signal]
            if strongest_title_signal > 0 and len(tied_by_title) == 1:
                tied = tied_by_title
            elif strongest_title_signal > 0:
                longest_title_phrase = max(
                    max((len(keyword) for keyword in score["title_hits"]), default=0)
                    for score in tied_by_title
                )
                tied_by_specific_phrase = [
                    score for score in tied_by_title
                    if max((len(keyword) for keyword in score["title_hits"]), default=0) == longest_title_phrase
                ]
                if longest_title_phrase > 0 and len(tied_by_specific_phrase) == 1:
                    tied = tied_by_specific_phrase
                else:
                    tied = []
            else:
                tied = []
        if not tied or best < 2:
            primary = TOPIC_BY_SLUG[OTHER_SLUG]
            confidence = "待复核"
            reason = "主题证据弱或多个主题接近"
        else:
            winner = tied[0]
            primary = TOPIC_BY_SLUG[winner["slug"]]
            confidence = "较高" if winner["title_hits"] else "中"
            reason = "标题命中主题词" if winner["title_hits"] else "分析/摘要命中主题词"

    return {
        "id": item["id"],
        "title": item["title"],
        "published_at": item.get("published_at", ""),
        "source_type": source_type,
        "source_label": source_label,
        "source_path": item["article_path"],
        "analysis_path": item.get("analysis_path"),
        "url": item.get("url", ""),
        "topic_slug": primary["slug"],
        "topic_title": primary["title"],
        "confidence": confidence,
        "classification_basis": basis,
        "classification_reason": reason,
        "candidates": scores[:3],
    }


def load_records(root: Path = ROOT) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for relative_path, source_type, source_label in SOURCES:
        catalog = json.loads((root / relative_path).read_text(encoding="utf-8"))
        records.extend(classify_entry(root, item, source_type, source_label) for item in catalog)
    ids = [record["id"] for record in records]
    if len(ids) != len(set(ids)):
        raise ValueError("Source catalogs contain duplicate entry IDs")
    return records


def markdown_link_title(title: str) -> str:
    return title.replace("\\", "／").replace("[", "［").replace("]", "］").replace("\n", " ").strip()


def relative_corpus_link(path: str) -> str:
    prefix = "corpus/"
    if not path.startswith(prefix):
        raise ValueError(f"Expected a corpus-relative path: {path}")
    return "../../" + path[len(prefix):]


def render_root_index(records: list[dict[str, Any]]) -> str:
    topic_counts = Counter(record["topic_slug"] for record in records)
    source_counts = Counter(record["source_type"] for record in records)
    lines = [
        "# 蔡叔 Skill 主题目录",
        "",
        f"当前共有 **{len(records):,} 条唯一知识条目**：752篇公众号原文、18篇简书交叉发布摘要、631条简书历史目录卡。公众号原文各配有一张分析卡；分析卡是配套解读，不另计为新文章。",
        "",
        "简书历史目录卡只含标题、发布日期、链接和最多36字列表导语，不是全文。简书标题匹配用于关联来源，不把同一记录重复计数。",
        "",
        "## 分类口径",
        "",
        "主题由确定性关键词规则分配：公众号原文使用标题和分析卡中的‘作者主张/可复用提炼’，简书摘要使用标题和摘要，历史简书目录卡使用标题和列表导语。每条只分配一个主目录；证据不足或多主题接近的条目标为‘综合与待复核’。这是一层导航，不替代全文检索、原文或分析卡。规则见 `scripts/build_topic_indexes.py`，分配结果与置信度见 `index.json`。",
        "",
        "## 主题目录",
        "",
        "| 目录 | 条目数 | 公众号原文 | 简书摘要 | 简书目录卡 |",
        "|---|---:|---:|---:|---:|",
    ]
    for topic in TOPICS:
        matching = [record for record in records if record["topic_slug"] == topic["slug"]]
        counts = Counter(record["source_type"] for record in matching)
        lines.append(
            f"| [{topic['title']}]({topic['slug']}/INDEX.md) | {topic_counts[topic['slug']]} | "
            f"{counts['wechat-original']} | {counts['author-crosspost-summary']} | {counts['author-jianshu-archive-listing']} |"
        )
    lines.extend([
        "",
        "## 原始语料目录",
        "",
        "- `../articles/`：公众号原文正文。",
        "- `../analysis/`：与公众号原文配对的整理者分析卡。",
        "- `../crossposts/`：近期简书交叉发布摘要。",
        "- `../jianshu_archive/`：历史简书来源目录卡。",
        "",
        "主题目录仅创建索引，没有搬移或复制原始条目，因此现有 ID、哈希和检索路径保持不变。",
        "",
    ])
    return "\n".join(lines)


def render_topic_index(topic: dict[str, Any], records: list[dict[str, Any]]) -> str:
    source_counts = Counter(record["source_type"] for record in records)
    lines = [
        f"# {topic['title']}",
        "",
        topic["description"],
        "",
        f"条目数：**{len(records):,}**（公众号原文 {source_counts['wechat-original']}；简书摘要 {source_counts['author-crosspost-summary']}；简书目录卡 {source_counts['author-jianshu-archive-listing']}）。",
        "",
        "分类是导航建议，依据标题及可用的分析摘要/列表导语；低置信条目集中在‘综合与待复核’。涉及具体判断时仍应打开原文和分析卡。",
        "",
        "## 内容清单",
        "",
    ]
    for record in records:
        date = record["published_at"][:10] if record["published_at"] else "日期未知"
        title = markdown_link_title(record["title"])
        source_link = relative_corpus_link(record["source_path"])
        if record["source_type"] == "wechat-original":
            links = f"[公众号原文]({source_link})"
            if record.get("analysis_path"):
                links += f" · [分析卡]({relative_corpus_link(record['analysis_path'])})"
        elif record["source_type"] == "author-crosspost-summary":
            links = f"[简书摘要]({source_link})"
        else:
            links = f"[简书目录卡]({source_link})"
        lines.append(f"- {date} · {links} · {title}")
    lines.append("")
    return "\n".join(lines)


def write_indexes(root: Path, records: list[dict[str, Any]]) -> list[dict[str, str]]:
    topic_root = root / TOPIC_ROOT
    topic_root.mkdir(parents=True, exist_ok=True)
    by_topic: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_topic[record["topic_slug"]].append(record)
    for entries in by_topic.values():
        entries.sort(key=lambda record: (record["published_at"], record["title"], record["id"]), reverse=True)

    (topic_root / "INDEX.md").write_text(render_root_index(records), encoding="utf-8", newline="\n")
    payload = {
        "schema_version": 1,
        "unique_entry_count": len(records),
        "source_counts": dict(sorted(Counter(record["source_type"] for record in records).items())),
        "classification_method": "One primary topic per entry. Deterministic keyword scores use title plus source-appropriate evidence; weak/tied results go to 99-综合与待复核.",
        "topics": [
            {
                "slug": topic["slug"],
                "title": topic["title"],
                "description": topic["description"],
                "entry_count": len(by_topic.get(topic["slug"], [])),
                "index_path": f"corpus/topics/{topic['slug']}/INDEX.md",
            }
            for topic in TOPICS
        ],
        "entries": sorted(records, key=lambda record: (record["topic_slug"], record["published_at"], record["id"])),
    }
    (topic_root / "index.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    for topic in TOPICS:
        directory = topic_root / topic["slug"]
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "INDEX.md").write_text(render_topic_index(topic, by_topic.get(topic["slug"], [])), encoding="utf-8", newline="\n")

    relative_paths = [
        path.relative_to(root).as_posix()
        for path in sorted(topic_root.rglob("*"))
        if path.is_file() and path.suffix.lower() in {".md", ".json"}
    ]
    return [
        {"path": path, "sha256": hashlib.sha256((root / path).read_bytes()).hexdigest()}
        for path in relative_paths
    ]


def update_manifest(root: Path, records: list[dict[str, Any]], index_files: list[dict[str, str]]) -> None:
    manifest_path = root / "corpus/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["topic_index"] = {
        "entry_count": len(records),
        "primary_topic_counts": dict(sorted(Counter(record["topic_slug"] for record in records).items())),
        "source_counts": dict(sorted(Counter(record["source_type"] for record in records).items())),
        "method": "Deterministic title and source-appropriate summary keyword scoring; one primary topic per unique catalog entry; low-confidence/tied records go to 99-综合与待复核.",
        "canonical_article_paths_moved": False,
        "files": index_files,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print category counts without writing indexes")
    args = parser.parse_args()
    records = load_records()
    counts = Counter(record["topic_slug"] for record in records)
    source_counts = Counter(record["source_type"] for record in records)
    print(f"Unique knowledge entries: {len(records)}")
    print("Sources: " + ", ".join(f"{key}={value}" for key, value in sorted(source_counts.items())))
    for topic in TOPICS:
        print(f"{topic['title']}: {counts[topic['slug']]}")
    if args.dry_run:
        return 0
    index_files = write_indexes(ROOT, records)
    update_manifest(ROOT, records, index_files)
    print(f"Wrote {len(index_files)} topic navigation files under {TOPIC_ROOT.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
