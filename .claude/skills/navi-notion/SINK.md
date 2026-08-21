# Notion 落库规范（navi-arxiv / navi-hfpapers / navi-zhihu 共用）

抓取类 skill 抓完后**除了在终端输出，还要把结果写进 Notion**，按日期归档。
本文件是三个 skill 共用的唯一一份规则，改格式只改这里。

## 页面树

```
<daily_root>                 ← 配置里给的根页面（如「Daily Info」）
└── 2026-0821                ← 日期页，一天一个，标题格式 %Y-%m%d
    ├── zhihu                ← 每个信息源一个子页，页名见配置
    ├── arxiv
    └── hfpaper
```

**只允许写今天的日期页**。往昨天的页面追加是错的——那会让历史那天的内容凭空多出一段。

## 配置

读 `$NAVI_HOME/notion-pages.md`（不存在则回退本目录 `notion-pages.example.md`）。
里面给 `daily_root` 页面 ID 与「skill → 子页名」映射。

**没有配置文件、或 Notion MCP 未接（工具不可用）时：跳过写入，只在终端输出**，
并在末尾一行告诉用户「未写入 Notion：缺 xxx」。不要为此报错中断，也不要去猜页面 ID。

## 流程

1. `Bash: date -u +%Y-%m%d` 取今天的日期串（**不要凭上下文里的日期硬写**）。
2. `mcp__notion__get_page(daily_root)` 列子页，找标题等于该日期串的页。
   - 找到 → 用它的 ID。
   - 没找到 → `mcp__notion__create_page(title=日期串, parent_id=daily_root, parent_type="page", markdown="")`。
3. `mcp__notion__get_page(日期页)` 列子页，找本次信息源对应的页名。
   - 没找到 → `create_page(title=页名, parent_id=日期页, parent_type="page", markdown=正文)`。
   - 找到（同日重跑）→ `mcp__notion__append_markdown` 追加，正文前先加一行 `---` 分隔。
     **不删已有内容**；同一天出现两段是预期行为，要不要清理由用户决定。
4. 把新建/更新的页面 URL 报给用户。

## 分批

Notion 一次最多收 100 个子块。一条正文里 `## 标题` / `---` / `### 标题` / 每个 `- ` 列表项
各算一块，所以**按信息源的段落切开多次 `append_markdown`，每次控制在 ≤90 块**
（经验值：arxiv 每篇 5 块，一次不超过 17 篇）。超了会写丢，且没有报错。

## 正文版式

各 skill 的「Notion 版式」小节自己规定，本文件只管页面树与流程。
共同要求：抬头一行写清**抓取时间（UTC）、条数、数据来源**，让人一眼看出这段是哪次抓的。
