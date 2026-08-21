---
name: navi-hfpapers
description: 获取 Hugging Face Daily Papers 今日热门论文
argument-hint: "[条数=全部] [关键词…]"
user-invocable: true
allowed-tools: WebFetch, WebSearch, Bash, Read, mcp__notion__get_page, mcp__notion__create_page, mcp__notion__append_markdown
---

# Hugging Face Daily Papers

## 参数

`$ARGUMENTS` 可选：

| 参数 | 默认 | 说明 |
|------|------|------|
| 条数（纯数字） | `10` | 输出前 N 条；给 `all` / `全部` 则不截断 |

其余词按关键词过滤标题（大小写不敏感），给了就只留命中的条目；一条都不命中时如实说明，不要放宽条件硬凑。

## 任务

获取 Hugging Face Daily Papers 今日热门论文并呈现给用户。

## 数据获取

使用 WebFetch 抓取 API：

```
https://huggingface.co/api/daily_papers?date={YYYY-MM-DD}&sort=trending
```

`date` 参数使用当天日期。返回 JSON 数组，列出全部结果。

从每个元素中提取：
- `paper.id` — arxiv ID，用于构造链接 `https://arxiv.org/abs/{id}`
- `paper.title` — 标题
- `paper.authors` — 作者列表，取每个元素的 `name` 字段
- `paper.summary` — 摘要
- `paper.upvotes` — 点赞数
- `paper.githubRepo` — GitHub 仓库链接（可能为空）
- `numComments` — 评论数

## 输出格式

```
## Hugging Face Daily Papers

────────────────────────────────────────
  #: 1
  标题: Paper Title (👍 42 💬 5)
  作者: Author1, Author2, ...
  摘要: 2-3 句中文摘要
  链接: https://arxiv.org/abs/xxxx.xxxxx
  代码: https://github.com/xxx/xxx
```

每篇论文之间用 `────────────────────────────────────────` 分隔。

## 格式要求

- **标题**：英文原标题 + 点赞数和评论数，格式为 `Title (👍 点赞 💬 评论)`
- **作者**：英文原名，最多列 5 位，超出用 `et al.`
- **摘要**：将英文摘要翻译/概括为 2-3 句中文
- **链接**：使用 `https://arxiv.org/abs/{paper.id}` 格式
- **代码**：仅在 `githubRepo` 非空时显示此行
- 列出全部论文，不要截断
- 除标题和作者外用中文输出

## 写入 Notion（抓完必做）

抓完**除了终端输出，还要按日期归档到 Notion**。流程与页面树见共享规范
`$S/../navi-notion/SINK.md`（`$S` 为本 skill 的 base directory；软链装法下等价于
`~/.claude/skills/navi-notion/SINK.md`），先读它再动手。

**Notion 版式**（子页名 `hfpaper`，与 08-19 那页保持一致，别改）：

```
抓取日期 2026-08-21 · 共 50 篇 · 来源 huggingface.co/api/daily_papers?sort=trending
### 1. Paper Title (👍 660 💬 4)
**作者**：Author1, Author2, Author3, Author4, Author5 et al.
**摘要**：2-3 句中文摘要
**链接**：[arxiv.org/abs/xxxx.xxxxx](https://arxiv.org/abs/xxxx.xxxxx) · **代码**：[owner/repo](https://github.com/owner/repo)
```

- `githubRepo` 为空时省掉 ` · **代码**：…` 这半句，不要留空链接
- 写**全部论文**，不受 `[条数]` 参数影响——终端可以截断，归档必须完整
- **每篇 4 个块**，一次 `append_markdown` 不超过 22 篇，按批切开多次追加
