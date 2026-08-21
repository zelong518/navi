---
name: navi
description: navi 总入口——把一句自然语言需求路由到具体能力：查论文（arxiv / HF Papers / 自己的 Zotero 库）、看热榜（知乎 / GitHub / HN / Product Hunt）、每日简报、训练任务与实验（DLC / SwanLab）、机器清单、Claude Code 与 Codex 状态快照、配置备份、推送出口（飞书 / 负一屏 / Notion）、Polymarket 资产与策略、以及性能排障与协作规范两套方法论。不确定该用哪个能力时也用它。
argument-hint: "<一句需求> 例：今天的 arxiv | 知乎话题 | 快照一下 | 查持仓 | 推飞书 | 列一下能做什么"
user-invocable: true
allowed-tools: Skill, Bash, Read, Write, WebSearch, WebFetch
---

# navi 总入口

把 `$ARGUMENTS`（一句自然语言需求）**路由**到下面的具体 skill，用 `Skill` 工具调用它，
并把**用户的原始需求原样传下去**（不要自己改写成子命令，子 skill 自己会解析）。

这个 skill 本身**不干活**，只做三件事：**认意图 → 调子 skill → 汇总输出**。

## 能力路由表

| 用户说的话里有 | 调用 | 备注 |
|---|---|---|
| arxiv / 今日论文 / 新论文 / 基模 / 训练系统 / 推理系统 / 可靠性 / 安全（论文语境） | `navi-arxiv` | 方向定义在 `$NAVI_HOME/arxiv-directions.md` |
| huggingface / hf / daily papers | `navi-hfpapers` | |
| 知乎 / 热榜（知乎语境）/ 话题 | `navi-zhihu` | `hot` 热榜、`topic` 话题 |
| github / 热门仓库 / trending | `navi-github` | |
| hacker news / hn | `navi-hackernews` | |
| product hunt / 新产品 | `navi-producthunt` | |
| 简报 / 日报 / 早报 / brief | `navi-brief` | 它会并行调多个信息源 |
| 我的论文库 / zotero / 问问我的论文 | `navi-paper` | |
| swanlab / 分析实验 / 指标关系 | `navi-swanlab-analyze` | |
| 盯训练 / 监控实验 / 有没有异常 | `navi-swanlab-monitor` | 配 `/loop` 可持续盯 |
| dlc / 训练任务 / 集群任务 / 谁在用卡 | `navi-dlc` | |
| 服务器 / 机器清单 / 哪台机器 / ssh 到 | `navi-server` | 清单含 GPU 容量与已知坑 |
| 快照 / 备份 claude / 恢复 claude / 重启前 | `navi-snapshot` | `upload` 存、`sync` 恢复 |
| 备份配置 / webdav / 换机恢复配置 | `navi-backup` | 备份的是 `$NAVI_HOME` |
| 推飞书 / 发飞书群 | `navi-feishu` | |
| 负一屏 / hiboard / 推到手机 | `navi-hiboard` | |
| polymarket / 预测市场 / 我的持仓 / 盈亏 / 策略 | `navi-polymarket` | 只读，不下单 |
| 性能 / 变慢 / 吞吐 / 延迟 / benchmark / 压测 / 排障 / 复现 | `navi-perf-discipline` | 方法论，不是取数 |
| 提 issue / 开 MR / commit 规范 / 能不能合 | `navi-devflow` | 方法论 |
| 推到 notion / 写进 notion | 用 `mcp__notion__*` 工具 | 见下方「推送到 Notion」 |

## 编排要求

1. **一个需求命中多个能力时，并行调用多个子 skill**（一条消息里发多个 `Skill` 调用），
   拿到结果再合并成一份输出。例：「抓今天的 arxiv 和知乎」→ 同时调 `navi-arxiv` 与 `navi-zhihu`。
2. **原始需求原样传给子 skill**。子 skill 的 `argument-hint` 里写了它自己的子命令与默认值，
   由它解析；上层不要越权翻译成 `hot 20` 这种参数，除非用户就是那么说的。
3. **需求里带「推送」类动作时分两步**：先调取数的 skill 拿到内容，再调推送的
   （`navi-feishu` / `navi-hiboard` / Notion）。推送正文用取数结果，**不要自己另编一份**。
4. **认不出意图**时不要猜，也不要硬塞一个最像的：把上面的能力表按类别摘要给用户，问他要哪个。
5. **`$ARGUMENTS` 为空**时不要报错——直接列能力清单（按「信息源 / 训练与集群 / 状态与配置 /
   推送出口 / 投资 / 方法论」六类），并告诉用户可以直接说需求。
6. 子 skill 报缺配置时，把它的原话转达并指出该在 `$NAVI_HOME/config.toml` 的哪个段补什么，
   **不要替用户编造凭证或跳过**。

## 推送到 Notion

Notion 走 MCP 工具（`mcp__notion__search` / `create_page` / `append_markdown` 等），
不要自己起脚本调 REST API。常见形态是「日期页 → 分类子页」：

1. `mcp__notion__search` 找目标父页（例如 `Daily Info`）
2. 用 `mcp__notion__get_page` 看它下面已有的日期页，**沿用现有命名约定**（不要自创格式）
3. 日期页不存在就 `create_page` 建；已存在则**复用**，不要重建
4. 分类子页（`arxiv` / `zhihu` / `hfpaper` 等）同理：不存在则建，已存在则追加
5. ⚠️ **要覆盖已有内容前必须先问用户**——归档/删除是不可逆动作（回收站可恢复，但别默认这么做）

MCP 未连接时（工具列表里没有 `mcp__notion__*`）先告诉用户去 `/mcp` 重连，
不要绕道自己写 REST 调用当默认路径。

## 跨仓库使用

navi 的 skill 装到用户级后可在**任何仓库**里调用，因此：

- 子 skill 的脚本路径一律用**调用时给出的 base directory** 拼绝对路径，
  不要用相对 cwd 的 `.claude/skills/...`（cwd 通常不是 navi 仓库根）
- 配置目录由 `NAVI_HOME` 决定，需在**用户级** `~/.claude/settings.json` 的 `env` 里设置；
  只写在 navi 项目的 `settings.json` 里，出了 navi 目录就读不到

## 文件结构

- `.claude/skills/navi/SKILL.md` — 本路由表（不含实现）
- `.claude/skills/navi-*/` — 各能力的实现，每个可单独用 `/navi-xxx` 调用
