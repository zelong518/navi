---
name: navi-zhihu
description: 知乎内容抓取——`hot` 取当前热榜（可按条数/关键词过滤），`topic` 抓某个话题相关的内容（知乎官方搜索接口需登录，故走 WebSearch 限定 zhihu.com），省略关键词时读 $NAVI_HOME/zhihu-topics.md 里的常关注话题清单。
argument-hint: "hot [条数=10] [关键词…] | topic [关键词…=常关注话题] | all"
---

# 知乎热榜

## 参数

`$ARGUMENTS` 第一个词是子命令，缺省按 `hot` 处理：

| 子命令 | 默认 | 说明 |
|--------|------|------|
| `hot [条数] [关键词…]` | 条数 10 | **热榜**。纯数字为条数（`all`/`全部` 不截断）；其余词按关键词过滤标题 |
| `topic [关键词…]` | 读常关注话题 | **话题相关内容**。省略关键词时读 `$NAVI_HOME/zhihu-topics.md` 里的清单逐个搜 |
| `all` | — | 热榜 + 全部常关注话题 |

一条都没命中时如实说明，**不要放宽条件硬凑**。

## topic 怎么抓（重要）

**知乎官方的搜索与话题接口都要登录**，实测：
`api.zhihu.com/search_v3` 返回 `40353 need_login`，`api/v4/topics/<id>/feeds` 返回
`10003 请求参数异常`（要客户端签名）。只有 `/topstory/hot-list` 可无鉴权访问。

所以 `topic` 走 **WebSearch 限定域名**，不碰知乎鉴权：

```
WebSearch(query="<话题关键词>", allowed_domains=["zhihu.com"])
```

- 关键词省略时：`Read` 读 `$NAVI_HOME/zhihu-topics.md`（不存在则回退同目录
  `zhihu-topics.example.md`），**每个话题一次 WebSearch**，可在一条消息里并发多个
- 命中的多是**专栏文章**（`zhuanlan.zhihu.com/p/...`）而非问答；这是搜索引擎索引的结果，
  **不是实时热度排序**，输出时要讲清这一点，别把它当成"话题热榜"
- 想看某篇的实际内容用 `WebFetch` 取该 URL，不要凭标题编摘要

## 任务

按子命令获取知乎内容并呈现给用户：`hot` 走下面的热榜接口，`topic` 走上面的 WebSearch 路径。

## 数据获取

使用 Codex 网页工具 抓取：

```
https://api.zhihu.com/topstory/hot-list?limit=50
```

对每个条目提取：
- `title` — 问题标题
- `url` — 问题链接（知乎问题页 URL，格式如 `https://www.zhihu.com/question/{id}`）
- `detail_text` — 热度描述（如 "xxx 万热度"）

## 输出格式

```
## 知乎热榜

────────────────────────────────────────
  #: 1
  话题: 问题标题 (🔥 xxx万)
  链接: https://zhihu.com/question/xxx
```

每个条目之间用 `────────────────────────────────────────` 分隔。

## 格式要求

- **话题**：显示问题标题原文，热度紧跟其后，格式为 `(🔥 xxx万)`
- **链接**：格式为 `https://zhihu.com/question/xxx`，不加 `www.`
- 列出所有热榜条目（通常 30 条），不要截断
- 用中文输出

## topic 的输出格式

```
## 知乎话题 — <关键词>
（来源：搜索引擎索引的 zhihu.com 内容，非实时热度排序）

────────────────────────────────────────
  标题: 文章标题
  类型: 专栏 / 问答
  要点: 1-2 句中文要点（读过正文才写，否则只给标题）
  链接: https://zhuanlan.zhihu.com/p/xxx
```

多个话题时按话题分节。每个话题下没结果就写「无命中」，不要用相邻话题的结果充数。
