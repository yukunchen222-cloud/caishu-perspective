# 蔡叔决策 Skill

以请辩公众号本地资料和作者公开交叉发布文章为依据的中文决策顾问。支持具体选择、方案比较、反方检验、行动验证与复盘。原文、整理者分析和来源范围分开标注，不依赖制作人的电脑路径。

## 安装和调用

下载或克隆本仓库，将**整个仓库内容**放入宿主的 `caishu-perspective` Skill 文件夹，不要只复制 `SKILL.md`。Codex 的用户目录一般是 `~/.codex/skills/caishu-perspective`；Claude Code 可使用 `~/.claude/skills/caishu-perspective`。如果宿主已有同名目录，先检查差异并备份，不直接覆盖。

公开仓库：[yukunchen222-cloud/caishu-perspective](https://github.com/yukunchen222-cloud/caishu-perspective)。

```bash
git clone https://github.com/yukunchen222-cloud/caishu-perspective.git caishu-perspective
```

下载后将整个 `caishu-perspective` 文件夹放入上述宿主 Skill 目录。不同宿主和系统的安装目录可能不同，请按对应工具的 Skill 安装说明定位；如果已存在同名目录，先检查差异并备份，不直接覆盖。

原始语料基线：[b98cdda96423571a31794334ee6d390f48fcc8df](https://github.com/yukunchen222-cloud/caishu-perspective/tree/b98cdda96423571a31794334ee6d390f48fcc8df)。本地当前构建保留752篇公众号原文、18篇作者简书交叉发布整理者摘要，并新增631条历史简书来源目录卡；后两类不是公众号原文，也不构成逐篇全文同步证明。

支持 Skill 的宿主刷新后调用：

```text
请用 $caishu-perspective 帮我做决策。
问题：<我究竟要决定什么>
选项：<A、B，以及维持现状>
目标：<我想得到的结果>
约束：<钱、时间、资源、义务、不能承受的后果>
请引用相关原文，给出推荐、最强反方、改判条件和一个验证动作。
```

例：是否应保留现职并先做 AI 服务试单，还是辞职投入？提供已有客户、收入、储备和时间后，再形成方案。资料不足时它会先问关键问题，不承诺知道作者对未发表问题的真实立场。

普通聊天工具不能自动访问电脑文件或执行 Skill。可上传本目录文件至其项目知识库，再让它读取 `SKILL.md`；实际能力取决于宿主的文件读取、检索和工具权限。

## 检索

Python 3.9 或更高版本，无第三方依赖：

```bash
python scripts/search.py "创业 成本 客户" --limit 5
python scripts/evidence.py "辞职 持续增量 机会成本" --limit 3
python scripts/search.py --read wxmp-b1f8ef1b75c5e77fce3d --kind article --max-chars 6000
python scripts/search.py "关键词" --sources listings --limit 5
```

也可从 [主题导航](references/topics.md) 打开本地 Markdown，不运行脚本。

默认检索只把公众号原文及近期简书整理者摘要作为决策材料；历史目录卡须显式使用 `--sources listings` 或 `--sources all`，仍不是全文。命中分析卡的片段明确标记整理者分析。`--as-of YYYY-MM-DD` 限定资料时间，`--exclude-id <ID>` 同时排除已知标题/正文/同源链接关联组，但不是语义近重复检测。

## 决策优化层

`scripts/evidence.py` 在同一次查询中分开返回原文候选、12条有正文定位的读者来信案例、8条跨来源条件化原则及辅助摘要。来信事实未经独立核实、结果未观察。案例和原则均从2025年及以前的已署名原文整理，保留来源行号、哈希、作者建议与应用边界；`editor_notes`单独标记整理者校正，不并入作者建议。不新增来源文章计数，也不声称已有长期效果。检索分数只表示词汇相关性。精确引用和重要取舍仍须阅读原文。

回答分开处理“原文支持的作者方向”与“适合用户目标和约束的建议”，保留作者激进/保守的不同分支，主动检查反向证据；用户事实、偏好、决定和结果单独保存，不回灌成作者原则。没有新建 Agent 应用、微调模型或改写原始语料。

复杂决策按 [交付结构](references/delivery-check.md) 把JSON草稿送入 `scripts/decision_gateway.py` 的stdin；校验成功才返回固定渲染的正文，失败不输出草稿，不再自由改写而漏掉来源或行动。`check_decision.py --input`仍可用于机器诊断，但它本身不是展示入口。

需要真正截留模型输出时，从本Skill目录运行 `python -X utf8 scripts/run_decision.py`，通过stdin提供问题；它调用已登录的本机Codex，以read-only/never/ephemeral方式生成结构化草稿，校验后才输出正文，不改模型配置、不复制凭据。完整参数与宿主接入方式见 [运行时接入](references/runtime-integration.md)。**强制拦截仅适用于经过该入口的调用**；普通GPT或直接聊天调用Skill没有自动变成同等宿主。结构通过仍不证明推理、反方质量或效果有效。

## ZIP分发版本

本轮版本为1.1.0。应使用`caishu-perspective-1.1.0.zip`或公开仓库最新完整目录；历史`caishu-perspective-1.0.0.zip`不含本轮新增案例与网关，不能冒称最新版。打包工具`python scripts/package_release.py --output <源仓库外的新ZIP路径>`只打包已提交且干净的Git快照，拒绝覆盖，逐文件检查ZIP正文对应的Git blob并返回提交、SHA-256与文件数。新ZIP不含本机Codex或登录态，接收者仍需自己的运行环境和登录。

评测见 [evals/README.md](evals/README.md)：32个任务来自8个独立留出案例及8个边界题，不能写成32个独立作者案例。运行题单不等于模型通过；技术检查与实际盲测结果分别记录在 [VERIFY.md](VERIFY.md)。

## 按主题浏览

打开 [主题目录总览](corpus/topics/INDEX.md)，可按财富与投资、创业与商业、职业与职场、学习与成长、婚恋与家庭关系、人生心理与身心状态、社会与公共议题、科技与行业趋势等目录浏览条目。每条保留原始 ID 和文件位置，并链接到公众号原文及配套分析卡，或对应的简书摘要/历史目录卡；语料文件没有搬移。

主题目录当前索引1,401条唯一知识条目：752篇公众号原文、18篇简书交叉发布摘要、631条简书历史目录卡。752张配套分析卡不是额外文章。简书历史目录卡只含标题、日期、链接和最多36字列表导语。自动分类基于标题及来源适配的分析/摘要文本；低置信或有歧义的条目归入“综合与待复核”，详见 `corpus/topics/index.json`。

## 内容与验证

- `SKILL.md`：调用边界与决策工作流。
- `references/`：方法、详细流程、主题导航。
- `corpus/articles/`：原文正文与来源元数据；省略可识别的独立“（完）”标记后的推广尾段，逐篇在 manifest 中记录。
- `corpus/analysis/`：752 篇公众号原文对应的整理者分析、反方和证据边界。
- `corpus/crossposts/`：18 篇近期作者简书交叉发布文章的整理者摘要；只保留标题、日期、来源链接与分析，不复制全文。
- `corpus/jianshu_archive/`：631 条历史简书来源目录卡；仅保留标题、日期、简书链接和最多36字的列表导语摘录，不含文章全文。
- `corpus/catalog.json`：752 篇公众号原文的检索目录。
- `corpus/crosspost_catalog.json`：18 篇作者简书交叉发布摘要的检索目录。
- `corpus/jianshu_archive_catalog.json`：631 条简书历史目录卡的检索目录；默认不混入决策证据，显式目录发现或按 ID 读取仍可用。
- `corpus/decision_cases.json`、`corpus/decision_principles.json`：带原文定位的案例和条件化原则；整理者提炼，不是新文章或作者逐字通则。
- `corpus/jianshu_history_reconciliation.json`：简书主页1,132条可读记录与当前语料的逐条标题映射与对照状态。
- `corpus/manifest.json`：范围、日期、来源分类、源文件与导出文件哈希。
- `tests/`：检索、来源一致性与现实决策验收。

当前构建保留752篇由用户提供的请辩公众号原文（截至2026-09-14）、18篇近期简书交叉发布整理者摘要（2026-09-15至2026-10-16），并新增631条历史简书来源目录卡（2016-04-14至2026-10-16）。对简书作者页1,132条可读记录按保留标点的标题键核对，501条简书记录匹配现有语料：483条映射到482篇公众号原文（1条简书重复发布）及18条现有简书摘要；631条未匹配记录独立作为简书来源收录。752篇公众号原文中270篇没有简书精确标题匹配。作者主页显示1,136篇，分页可读到1,132条，4条差额原因未知。历史卡不含全文，导语最多36字；用户确认内容同源，但没有逐篇对公众号原文全文比对。图片文字未 OCR，评论未采集。作者观点、读者来信、整理者分析与本次框架应用分别处理。

源库只读导出，未包含 HTML、SQLite、登录态、API Key 或个人记忆。见 [资料与许可说明](NOTICE.md)。
