# 蔡叔决策 Skill

以请辩公众号本地资料和作者公开交叉发布文章为依据的中文决策顾问。支持具体选择、方案比较、反方检验、行动验证与复盘。原文、整理者分析和来源范围分开标注，不依赖制作人的电脑路径。

## 安装和调用

下载或克隆本仓库，将**整个仓库内容**放入宿主的 `caishu-perspective` Skill 文件夹，不要只复制 `SKILL.md`。Codex 的用户目录一般是 `~/.codex/skills/caishu-perspective`；Claude Code 可使用 `~/.claude/skills/caishu-perspective`。如果宿主已有同名目录，先检查差异并备份，不直接覆盖。

公开仓库：[yukunchen222-cloud/caishu-perspective](https://github.com/yukunchen222-cloud/caishu-perspective)。

```bash
git clone https://github.com/yukunchen222-cloud/caishu-perspective.git caishu-perspective
```

下载后将整个 `caishu-perspective` 文件夹放入上述宿主 Skill 目录。Windows 的 Codex 用户目录一般为 `C:\Users\你的用户名\.codex\skills\caishu-perspective`。如果已存在同名文件夹，先备份，不直接覆盖。

原始语料基线：[b98cdda96423571a31794334ee6d390f48fcc8df](https://github.com/yukunchen222-cloud/caishu-perspective/tree/b98cdda96423571a31794334ee6d390f48fcc8df)。当前版本保留其 752 篇公众号原文，并补充 18 篇作者简书交叉发布的整理者摘要；摘要不是公众号原文，也未验证为公众号完整更新清单。

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
python scripts/search.py --read wxmp-b1f8ef1b75c5e77fce3d --kind article --max-chars 6000
```

也可从 [主题导航](references/topics.md) 打开本地 Markdown，不运行脚本。

## 内容与验证

- `SKILL.md`：调用边界与决策工作流。
- `references/`：方法、详细流程、主题导航。
- `corpus/articles/`：原文正文与来源元数据；省略可识别的独立“（完）”标记后的推广尾段，逐篇在 manifest 中记录。
- `corpus/analysis/`：752 篇公众号原文对应的整理者分析、反方和证据边界。
- `corpus/crossposts/`：18 篇作者简书交叉发布文章的简要分析；只保留标题、日期、来源链接与整理者摘要，不复制全文。
- `corpus/catalog.json`：752 篇公众号原文的检索目录。
- `corpus/crosspost_catalog.json`：18 篇作者简书交叉发布摘要的检索目录；命令行检索会同时搜索两份目录。
- `corpus/manifest.json`：范围、日期、源文件与导出文件哈希。
- `tests/`：检索、来源一致性与现实决策验收。

原文快照包含 752 篇由用户提供的请辩公众号文章，发布时间截至 2026-09-14；另据作者简书主页收录 18 篇 2026-09-15 至 2026-10-16 的交叉发布摘要。后者不是微信公众号原文，公众号链接和发布时间未逐篇核实，不能宣称公众号已完整同步。日期、数量和边界以 manifest 为准。图片文字未 OCR，评论未采集。作者观点、读者来信、整理者分析与本次框架应用分别处理。

源库只读导出，未包含 HTML、SQLite、登录态、API Key 或个人记忆。见 [资料与许可说明](NOTICE.md)。
