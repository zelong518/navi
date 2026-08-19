---
name: navi-arxiv
description: 获取今日 arxiv 论文并按你的关注方向筛选（默认五类：大语言模型基模 / 训练系统 / 推理系统 / 可靠性与故障观测 / 大模型安全）。方向定义读 $NAVI_HOME/arxiv-directions.md，改方向不用改 skill。
argument-hint: "[方向…=全选：基模|训练系统|推理系统|可靠性|安全] [条数=全部]"
user-invocable: true
allowed-tools: Bash, Read
context: fork
---

# arxiv 今日论文筛选

## 参数

`$ARGUMENTS` 可选：

| 参数 | 默认 | 说明 |
|------|------|------|
| 方向 | 全选 | `基模` / `训练系统` / `推理系统` / `可靠性` / `安全`，可多给；只输出命中方向 |
| 条数（纯数字） | 全部 | 每个方向最多输出 N 篇 |

## 任务

从 arxiv 获取今日新论文，筛选出与 **大语言模型基模**、**训练系统** 和 **大模型安全** 相关的论文，并以结构化格式呈现。

## 数据获取

用 `fetch.py` 取数，**不要用 WebFetch**——WebFetch 抓 RSS 只返回前 ~50 条就截断，
而当日 feed 常有 500+ 条，会漏掉绝大多数论文。

```bash
python3 .claude/skills/navi-arxiv/fetch.py > /tmp/arxiv-today.json
```

脚本自取 RSS 全量（`rss.arxiv.org`，cs.AI+cs.CL+cs.LG+cs.CE+cs.DB+cs.DC+cs.MA+cs.OS+cs.SY），
周末/假期 RSS 为空时自动回退 arxiv API。输出 JSON：

| 字段 | 说明 |
|------|------|
| `source` | `rss` 或 `api`（回退时） |
| `feed_date` | feed 的 pubDate，**输出时如实报告**（arxiv 通常凌晨才滚动，早上跑可能仍是昨天的） |
| `total_fetched` | 抓到的原始条目数 |
| `announced_today` | 剔除 `replace` 后的当日新公告数 |
| `papers[]` | `title` / `link` / `authors` / `abstract` / `announce_type`（`new` 或 `cross`） |

脚本默认剔除 `replace` / `replace-cross`（旧论文的更新，非今日新公告）；需要保留时加 `--keep-replace`。

**筛选在 JSON 上做**：用 Read 读取该文件，按下面的筛选规则逐条判断。条目数多（数百条），
逐条读标题与摘要，不要因为量大而只看前若干条。

## arXiv 分类代码

分类可用 `$NAVI_HOME/config.toml` 的 `[arxiv].categories` 覆盖（列表或 `+` 连接的字符串）；
默认已含 `cs.SE` / `cs.PF` / `cs.AR`（为可靠性与推理系统方向补的，实测只多约 30 条）。


| 代码 | 全称 | 说明 |
|------|------|------|
| cs.AI | Artificial Intelligence | 人工智能 |
| cs.CL | Computation and Language | 计算与语言（NLP） |
| cs.LG | Machine Learning | 机器学习 |
| cs.DC | Distributed, Parallel, and Cluster Computing | 分布式与并行计算 |
| cs.DB | Databases | 数据库 |
| cs.CE | Computational Engineering | 计算工程 |
| cs.MA | Multiagent Systems | 多智能体系统 |
| cs.OS | Operating Systems | 操作系统 |
| cs.SY | Systems and Control | 系统与控制 |

## 筛选规则

**规则不在本文件里**——读 `$NAVI_HOME/arxiv-directions.md`（不存在则回退同目录
`arxiv-directions.example.md`）。那份文件定义每个方向收什么、不收什么、边界怎么划，
以及兜底的「相关系统方向」。**用户改关注点只需要改那一个文件**，不用动 skill。

默认五个方向：大语言模型基模 / 训练系统 / 推理系统 / 可靠性与故障观测 / 大模型安全。

筛选时**理解论文主题**，不要只做关键词匹配；一篇只进一个方向，按最贴近其主要贡献的那个。
方向文件里写了同时命中时怎么裁（例如「更快更省」归系统方向、「更可靠更可诊断」归可靠性）。

## 输出格式

```
## arxiv 今日筛选

────────────────────────────────────────
  #: 1
  标题: Paper Title
  作者: Author1, Author2, ...
  摘要: 2-3 句中文摘要
  链接: http://arxiv.org/abs/xxxx.xxxxxv1
```

每篇论文之间用 `────────────────────────────────────────` 分隔。

主列表之后，若有通用训练/系统方向的论文，追加一节（同样逐条列出，格式一致）：

```
## 相关系统方向（非面向 LLM 训练）

────────────────────────────────────────
  #: 1
  标题: Paper Title
  作者: Author1, Author2, ...
  摘要: 2-3 句中文摘要
  链接: http://arxiv.org/abs/xxxx.xxxxxv1
```

若该节无论文则整节省略。

## 注意事项

- 所有非论文原文的内容用中文输出
- 在开头注明数据来源（`source`）、`feed_date`、以及「抓取 N 条 → 剔除 replace 后当日新公告 M 篇」
- `feed_date` 若不是今天（arxiv 尚未滚动），如实说明这批是哪天的，不要写成今天的
- 如果筛选后没有相关论文，明确告知用户
- 如果今天完全没有新论文（周末），告知用户 arxiv 周末不更新，并展示最近提交的相关论文
