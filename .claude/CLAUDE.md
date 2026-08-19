# Navi — 每日助手

这个仓库包含 Claude Code skills，用于论文追踪、GitHub 热榜和知乎热榜：

## Skills

| 命令 | 说明 |
|------|------|
| `/navi-arxiv` | 筛选今日 arxiv 上 LLM 基模、训练系统和大模型安全相关论文 |
| `/navi-paper sync\|ask\|status` | Zotero 论文库同步 + PaperQA2 语义问答（带引用）|
| `/navi-github [language]` | GitHub 每日热门仓库，支持按语言筛选 |
| `/navi-zhihu` | 知乎当前热榜话题 |
| `/navi-hfpapers` | Hugging Face Daily Papers 今日热门论文 |
| `/navi-hackernews` | Hacker News 当前热门帖子 |
| `/navi-producthunt` | Product Hunt 今日热门产品 |
| `/navi-brief` | 每日简报，聚合以上所有信息源；可选一并推送飞书群（无参数时弹窗询问）|
| `/navi-swanlab-analyze [实验]` | 分析 SwanLab 训练实验，自动挖掘指标关系并诊断 |
| `/navi-swanlab-monitor [实验]` | 实时监控运行中的训练实验，研判异常并告警（配 `/loop`） |
| `/navi-server add\|list\|remove` | 管理远程服务器清单（名字/IP/登录方式）|
| `/navi sync\|pull\|status` | 把 `~/.navi`（config + cache）镜像备份到 WebDAV，换机可恢复 |
| `/navi-hiboard` | 把任务结果推送到华为/荣耀手机「负一屏」（HiBoard 服务动态）|
| `/navi-feishu 「内容」` | 把内容推送到飞书群自定义机器人（webhook，KEY 可传参或配置）|
| `/navi-perf-discipline` | 性能测量与排障纪律（先测上限、交错 A/B、replay-first、证据强弱）|
| `/navi-devflow` | issue / MR / commit 规范与合并门禁 |
| `/navi-snapshot upload\|sync\|list\|prune` | 把本地 Claude Code / Codex 的工作状态（配置+会话+凭证+插件）快照到持久目录，重启后一条命令恢复 |
| `/navi-polymarket assets\|positions\|market\|strategy\|analyze` | 查 Polymarket 资产/持仓/行情 + 本地策略库 + 持仓分析（只读，不下单）|
| `/navi-dlc list\|logs\|workspaces` | 查阿里云 PAI-DLC 训练任务（跨工作空间列 Running + 卡数/时长/属主，取节点日志）|

## Paper — Zotero 论文库语义问答

把 Zotero 的 PDF 同步到本地，用 [PaperQA2](https://github.com/Future-House/paper-qa) 建索引/向量，命令行对自己的论文库做**带引用的语义问答**。LLM 与 embedding 走 SiliconFlow（OpenAI 兼容）。

设计原则：**取数自包**（`zotero_sync.py` 纯 stdlib 走 Zotero API + WebDAV，md5 去重）+ **核心交给 PaperQA2**（解析/切块/向量/检索/引用），skill 只编排 CLI。

```bash
pip install -r .claude/skills/navi-paper/requirements.txt   # 依赖 paper-qa
python3 .claude/skills/navi-paper/paper.py sync             # 同步 + 建索引（增量；--full 重建）
python3 .claude/skills/navi-paper/paper.py ask "问题"       # 带引用问答（省略问题进交互式）
python3 .claude/skills/navi-paper/paper.py status           # 查看 cache / 索引
```

文件结构：
- `.claude/skills/navi-paper/paper.py` — CLI 入口（sync / ask / status）
- `.claude/skills/navi-paper/config.py` — 读配置 + 构造 PaperQA `Settings`（处理 SiliconFlow 的 `encoding_format` 与 gpt-4o 默认值覆盖）
- `.claude/skills/navi-paper/zotero_sync.py` — 自包同步（Zotero API + WebDAV + md5 去重）

配置：`~/.navi/config.toml` 的 `[paper]`（cache + SiliconFlow key + 模型）与 `[zotero]`（API key + WebDAV）。可挂 cron 每日 `paper sync` 增量同步。

## MCP — 思源笔记 / Notion

通过 MCP Server 连接笔记软件，让 Claude 直接读写笔记。配置在仓库根 `.mcp.json` 中（Claude Code 只从 `.mcp.json` / `~/.claude.json` 读取 MCP server，不读 `settings.json`）；`.mcp.json` 已被 gitignore，需本机自建：

```json
{
  "mcpServers": {
    "notion": { "command": "node", "args": ["mcp/notion/index.js"] },
    "siyuan": { "command": "node", "args": ["mcp/siyuan/index.js"] }
  }
}
```

### 思源笔记

文档创建 / 编辑 / 搜索、块增删改、SQL 查询。凭证读 `[siyuan]` 段。

- `mcp/siyuan/index.js` — MCP Server 实现
- `mcp/siyuan/package.json` — 依赖声明

### Notion

读：`search`（只搜标题）/ `get_page`（正文递归转 markdown）/ `query_database` / `get_database`（看 schema）/ `list_databases`；
写：`create_page` / `append_markdown` / `update_block` / `update_page`（含归档）/ `delete_block`。

设计原则：**读写都以 markdown 为界面**——Notion API 只收 block 数组，`markdown.js` 做纯函数双向转换（标题/嵌套列表/待办/引用/代码块/表格/行内格式），Notion 的两条硬限制（rich_text ≤ 2000 字符、children ≤ 100/次）在转换层与 `appendBlocks` 里自动兜住。

- `mcp/notion/index.js` — MCP Server 实现（认证 / 工具 / 分页分批）
- `mcp/notion/markdown.js` — Notion block ⇄ markdown 双向转换
- `mcp/notion/README.md` — 拿 token、连接集成、已知边界

配置：`[notion]` 段，`token` 必填（集成的 Internal Integration Secret），`database_id` 可选（`create_page` 默认父级）。**建集成后必须去目标页面 `···` → 连接 → 添加集成**，否则一律 `object_not_found`；加在父页面上子页面自动继承。API 版本固定 `2022-06-28`（`2025-09-03` 起 database 拆成了 data source，`parent` 语义会变），别随手改。

## SwanLab 训练实验分析 / 监控

从 SwanLab（支持自建/云）读取大模型训练实验的原始指标，**自动挖掘指标间关系**（相关 / 领先滞后 / 同步变点 / 指标族离群）并诊断；运行中实验可**实时监控**。分析与监控**拆成两个独立 skill**，各司其职。

设计原则：**最小职责**——取数全部走 `tools/` 下的单一功能脚本（一个脚本只干一件事），脚本只回**裸数据**（不算统计、不判异常）；分析由 `swanlab-analyst` agent 完成；skill 只负责编排。

文件结构：
- `.claude/skills/navi-swanlab-analyze/SKILL.md` — 分析编排器（深度挖掘关系 + 诊断）
- `.claude/skills/navi-swanlab-monitor/SKILL.md` — 监控编排器（单周期研判，配 `/loop` 持续盯）
- `.claude/skills/navi-swanlab/` — **两个 skill 共享的资产包**（无 SKILL.md）
  - `tools/` — 单一功能取数脚本（凭证读 `~/.navi/config.toml`）
    - `_common.py` — 共享管线（读配置→构造 `swanlab.Api`），非工具
    - `list_projects.py` / `list_experiments.py` — 列项目 / 列实验
    - `get_summary.py` — 实验指标 summary（兼做指标发现）
    - `get_metrics.py` — 原始折线点（支持 `--all` / `--tail` / `--since-step` / `--out csv`）
  - `metrics.example.md` — **指标说明默认模板**
- `.claude/agents/swanlab-analyst.md` — 指标分析 agent（pandas 挖掘关系 + 诊断）

**指标说明（用户唯一需维护的文件）**：`~/.navi/swanlab-metrics.md`（不存在则回退到 `metrics.example.md`）。
只描述「单个指标是什么」（含义/期望趋势/健康范围/异常信号）；**指标之间的关系由 workflow 自动从数据挖掘**，无需手写，文末可选填强耦合先验。

依赖：`pip install -U swanlab`（需 >=0.8.0，提供 `swanlab.Api`）。

## Polymarket — 资产 / 持仓 / 策略

查 Polymarket 预测市场的资产估值、持仓明细、成交流水、单市场行情（订单簿深度/价差/价格历史），
并管理本地策略库、对持仓做分析。

**⛔ 只读边界**：不下单、不签名、不碰私钥。所有端点都是公开只读的，只需要一个**公开钱包地址**
（proxy wallet，`polymarket.com/profile/0x...` 里那串）。下单是不可逆的真金白银操作，
不在本 skill 范围内。

设计原则：**取数走公开 API，判断交给模型**——`analyze` 只吐裸数据（持仓 + 每仓实时
mid/spread/一周区间 + 流水），结论由 SKILL.md 的编排规则约束模型给出；脚本只做求和排序。

三组已实测端点（2026-08）：`data-api` 的 `/value` `/positions` `/activity`（账户），
`gamma-api` 的 `/markets`（元数据），`clob` 的 `/book` `/midpoint` `/spread` `/prices-history`（行情）。

```bash
python3 .claude/skills/navi-polymarket/polymarket.py assets            # 估值/成本/盈亏/可赎回
python3 .claude/skills/navi-polymarket/polymarket.py positions --sort pnl
python3 .claude/skills/navi-polymarket/polymarket.py market <slug> --history 1m
python3 .claude/skills/navi-polymarket/polymarket.py strategy add <名字> --file s.md
python3 .claude/skills/navi-polymarket/polymarket.py analyze <策略名>   # 裸数据 JSON
```

编排里有两条实质规则值得单独记：**簿内深度 < 仓位市值时要点明「按现价估的市值是虚的」**
（预测市场最容易骗人的地方），以及**只有 `redeemable` 且价值 >0 才提醒去 redeem**
（价值归零的已结算仓位赎无可赎）。

策略是本地 markdown（`$NAVI_HOME/polymarket/strategies/*.md`，含论点/标的/入场/出场/
仓位风控/复盘六节模板），`strategy add` 同名会覆盖并留 `.md.bak`；**不上传到任何外部服务**，
想跨机同步走 `/navi sync`。

配置：`[polymarket].address` 必填，`strategies` 可选。

## 知识型 skill — perf-discipline / devflow

两个**只讲方法、不含环境信息**的 skill，从实战项目里抽出来：

| skill | 内容 |
|-------|------|
| `perf-discipline` | 测量纪律（先测硬件上限、单次测量不可信要交错多轮、微基准排名不能外推到端到端、约 6% 中位差不足以行动、A/B 两 arm 冷热必须一致）；排障 replay-first 并按成本递增收缩；证据强弱表（分数是弱证据，**逐字相同**才是强证据）|
| `devflow` | issue 五段（含用矩阵表呈现单变量对照）、MR 五段（What / Why it broke / Changes / How verified / Risk）、conventional commit、分支命名、合并前门禁（⚠️ 增量构建不会更新已 import 的动态库，不重装就是在测旧代码）|

设计原则：**抽象入仓库，具体留本地**。环境实测常数、机器清单、仓库地址与凭据
一律放 `$NAVI_HOME`，仓库里只放 `.example.md` 模板：

- `$NAVI_HOME/cluster-facts.md` ← `navi-perf-discipline/cluster-facts.example.md`
  （存储/总线带宽上限、时间常数、已否掉的方向、环境特有的坑）
- `$NAVI_HOME/devflow.md` ← `navi-devflow/devflow.example.md`
  （各仓库 host / 项目 / git 身份 / token scope 要求 / 是否禁止 AI 署名）
- 机器清单走 `/navi-server`（写进 `$NAVI_HOME/config.toml` 的 `[servers.*]`，
  `note` 字段记 GPU 型号容量、内网 IP、已知坑）

沿用 `swanlab-metrics.md` 的既有模式：**用户唯一需维护的文件在 `$NAVI_HOME`，仓库只给模板。**

## Snapshot — Claude Code / Codex 状态快照

开发机的 home 常常不是持久存储，重启后 `~/.claude` 与 `~/.codex` 被清空——登录态、
会话记录、装好的插件全没了，而 `/volume` 这类挂载是持久的。本 skill 把两个工具的
**完整工作状态**存到持久目录，重启后一条 `restore` 复活。

设计原则：**白名单 + 可验证**——只收明确列出的配置/会话/凭证/插件项（纯运行时缓存
如 `cache/`、`ide/`、`tmp/` 不收），manifest 记录每文件 md5，`restore` 先校验再写回，
被覆盖的原文件自动备份到 `~/.navi-pre-restore-<时间戳>/`。纯 stdlib，无依赖。

两个工具的存储形态不同：Claude Code 是 jsonl（`projects/`、`history.jsonl`），
Codex 把会话/记忆存在带版本号的 sqlite 里（`state_5.sqlite` / `memories_1.sqlite`），
所以白名单支持 glob，且 sqlite 走 **backup API** 取一致快照（直接 `cp` 遇 WAL 会撕裂）。

```bash
python3 .claude/skills/navi-snapshot/snapshot.py upload           # 存时间戳快照并更新 latest
python3 .claude/skills/navi-snapshot/snapshot.py upload 重启前     # 命名槽位，同名再 upload 即更新
python3 .claude/skills/navi-snapshot/snapshot.py sync --dry-run   # 用 latest，先看会动什么
python3 .claude/skills/navi-snapshot/snapshot.py sync 重启前       # 指定快照恢复
python3 .claude/skills/navi-snapshot/snapshot.py list / prune 10
```

默认**全量**（配置 + 会话 + 凭证 + 插件），瘦身用 `--no-history` / `--no-credentials` /
`--no-plugins`；`--archive` 打成单个 tar.gz，`--keep N` 只留最近 N 份，
`--project DIR` 额外收项目级 `.claude`/`.codex`/`.agents`。

`upload <名字>` 是**命名槽位**：重复 upload 同名会原子替换（先写临时目录、成功才换上去），
且永不被滚动清理删除；不给名字则是时间戳快照，参与 `--keep` / `prune`。
`sync` 省略参数用 `latest`，也可给名字 / `snapshot-名字` / 路径 / `.tar.gz`。

**所有 skill 的 `argument-hint` 都写明了子命令、参数与默认值**，
在 Claude Code 里敲 `/navi-` 就能在补全里看到可用操作，不必翻文档。

文件结构：
- `.claude/skills/navi-snapshot/SKILL.md` — 编排说明
- `.claude/skills/navi-snapshot/snapshot.py` — CLI 入口（save / list / restore）

配置：`$NAVI_HOME/config.toml` 的 `[snapshot]` 段，`dest`（快照目录，**必须在持久存储上**）
与 `keep`（保留份数）。**快照含明文凭证**，所以快照目录设 `700`、凭证副本设 `600`，
且 `snapshots/` 已排除在 `navi sync` 之外，不会被上传 WebDAV。恢复后需重启 Claude Code。

挂 cron 每小时一份、留最近 24 份，重启最多丢 1 小时：

```cron
0 * * * * cd /path/to/navi && NAVI_HOME=/your/config python3 .claude/skills/navi-snapshot/snapshot.py upload --keep 24 >> /tmp/navi-snapshot.log 2>&1
```

## Navi 配置/缓存 WebDAV 备份

把整个 `~/.navi/`（`config.toml` + `paper-cache/` + `swanlab-metrics.md` 等）镜像到 WebDAV，多机同步 / 换机恢复。URL 与 WebDAV 账号全部写在 `[navi]` 段（`webdav_url` / `webdav_user` / `webdav_password`），独立配置，不复用其它段。

设计原则：**取数自包**（`webdav.py` 纯 stdlib，PROPFIND/PUT/GET/DELETE，跟随 alist 的 302 直链；OSS 后端目录隐式，靠 PUT 隐式建路径）+ **增量**（`~/.navi/.navi-sync.json` 记每文件 md5，未变跳过；日志/锁/`__pycache__` 不传）。

```bash
python3 .claude/skills/navi/navi.py sync             # 本地 → WebDAV（增量；--delete 真镜像）
python3 .claude/skills/navi/navi.py pull             # WebDAV → 本地（换机恢复）
python3 .claude/skills/navi/navi.py status           # 看本地与远端差异
```

文件结构：
- `.claude/skills/navi/navi.py` — CLI 入口（sync / pull / status）
- `.claude/skills/navi/webdav.py` — 极简 WebDAV 客户端

可挂 cron 每日 `navi sync` 增量备份。`[navi]` 段三项必填：`webdav_url` / `webdav_user` / `webdav_password`。

## Hiboard — 负一屏推送

任务完成后把 markdown 结果推送到华为/荣耀手机「负一屏」（HiBoard 服务动态）。原理是一次
HTTPS POST 到负一屏云端点，body 带 `authCode` + 一条 `msgContent`（markdown 正文）。

设计原则：**极简自包**——`push.py` 纯 stdlib（`urllib` + `tomllib`），只做「读配置 → 拼
标准 payload → POST → 解析响应码」，无外部依赖。

```bash
python3 .claude/skills/navi-hiboard/push.py --data task.json          # 推送（JSON 文件，格式最稳）
python3 .claude/skills/navi-hiboard/push.py --data task.json --dry-run # 只看 payload 不发
```

文件结构：
- `.claude/skills/navi-hiboard/SKILL.md` — 编排说明
- `.claude/skills/navi-hiboard/push.py` — CLI 入口（读配置 + 构造 payload + 推送）

配置：`~/.navi/config.toml` 的 `[hiboard]` 段，`auth_code` 必填（手机负一屏 → 我的 →
动态管理 → 关联账号 → Claw 智能体 获取），`push_url` 可选（默认华为云端点）。

## Feishu — 飞书群机器人推送

把 markdown 内容推送到飞书群「自定义机器人」。webhook 形如
`https://open.feishu.cn/open-apis/bot/v2/hook/<KEY>`，**KEY 可传参（`--key`，优先）
或写进配置**。无标题走 `text` 消息，带 `--title` 自动升级为 `interactive` 卡片
（正文按 `lark_md` 渲染 markdown）。

设计原则：**极简自包**——`push.py` 纯 stdlib（`urllib` + `tomllib`），读入参/配置的
KEY → 拼 payload → POST → 解析 `code`，无外部依赖。

```bash
python3 .claude/skills/navi-feishu/push.py --key <KEY> --content report.md        # 纯文本
python3 .claude/skills/navi-feishu/push.py --key <KEY> --title 简报 --data task.json # markdown 卡片
python3 .claude/skills/navi-feishu/push.py --data task.json --dry-run             # 只看 payload
```

文件结构：
- `.claude/skills/navi-feishu/SKILL.md` — 编排说明
- `.claude/skills/navi-feishu/push.py` — CLI 入口（KEY 参数优先，回退 `[feishu].key`）

配置：`~/.navi/config.toml` 的 `[feishu]` 段可选填 `key`（`--key` 未传时用）与 `base_url`
（默认飞书官方端点）。机器人若开了「签名校验」本 skill 不支持，请改用「自定义关键词」。

## DLC — 阿里云 PAI-DLC 任务查询

用阿里云官方 SDK 读训练任务列表与日志。先 `ListWorkspaces` 拿到你能访问的**全部**工作空间，
再逐个 `ListJobs`（`show_own=False`），这样看得到同事在同一工作空间的任务；GPU 卡数 / 已运行时长 /
属主（真人名 `username`）都取自 `ListJobs` 返回项，列表无需逐个 `GetJob`，只有 `logs` 才按 pod 取。

设计原则：**取数交给官方 SDK**，skill 只编排 + 中文小结；`list` 默认只列 `Running` 且滤掉 GPU=0
的辅助任务（convert-ckpt 等），并给出合计卡数与「我 vs 他人」拆分。

```bash
pip install alibabacloud_pai_dlc20201203 alibabacloud_aiworkspace20210204 alibabacloud_tea_openapi
python3 .claude/skills/navi-dlc/dlc.py list                    # 全部 Running（跨工作空间 + 合计卡数）
python3 .claude/skills/navi-dlc/dlc.py logs <jobid> --lines 50 # 最后一个节点的日志尾部
python3 .claude/skills/navi-dlc/dlc.py workspaces              # 列可访问工作空间
```

文件结构：
- `.claude/skills/navi-dlc/SKILL.md` — 编排说明
- `.claude/skills/navi-dlc/dlc.py` — CLI 入口（list / logs / workspaces）

配置：`~/.navi/config.toml` 的 `[dlc]` 段（`access_key_id` / `access_key_secret` / `region`，
`workspace_id` 可选）。**务必用 RAM 子账号只读密钥**，别用主账号 AK。

### 巡检 agent（dlc-inspector）

`.claude/agents/dlc-inspector.md` —— 训练集群值守 agent。用 `navi-dlc` skill 列全部 Running 任务、
并行取每个任务最后节点日志，逐个研判（🔴 HANG 挂起 / nan / loss 崩坏，⚠️ 数据加载抖动 / 吞吐骤降，
✅ 正常，含进度与预估完成时间），整理成分级报告并用 `navi-hiboard` skill 推送负一屏、`navi-feishu` skill
推送飞书群。取数/告警全走 skill 的脚本，自己不碰 API；只告警不改任务。**飞书 KEY 在触发时以参数
给出、不落盘**，不给则只推负一屏。可配 `/loop` 定时值守：

```
用 dlc-inspector agent 巡检一次 DLC 任务并推送负一屏
用 dlc-inspector agent 巡检 DLC 任务，飞书 KEY 用 1b64311b-...，推送负一屏和飞书
```

## tmux-claude-status

tmux 插件，通过 Claude Code hooks 实时追踪所有 Claude 实例状态，`prefix + a` 弹窗查看。

```bash
# 安装（写入 hooks 到 ~/.claude/settings.json + tmux 快捷键）
bash integrations/tmux-claude-status/install.sh

# 卸载
bash integrations/tmux-claude-status/install.sh --uninstall
```

文件结构：
- `integrations/tmux-claude-status/status-hook.sh` — hook 脚本，事件触发时写状态到 `/tmp/claude-status/`
- `integrations/tmux-claude-status/claude-status.sh` — 弹窗显示脚本
- `integrations/tmux-claude-status/statusline.sh` — 状态栏组件，有 approval 时显示 ✨
- `integrations/tmux-claude-status/install.sh` — 安装/卸载

## token-statusline — Token 用量状态栏

在 Claude Code 状态栏**常驻一行**显示模型 / 上下文 / 订阅额度 / 燃烧速率 / 今日总 token，
把 claude-hud（上下文%）+ ccusage（燃烧速率、今日 token）+ hook 原生 `rate_limits`（5h 额度）
合成一行：

```
🤖 Opus 4.8 | 🧠 61% (92k) | ⏳ 5h 42% (1h5m) | 🔥 $23.7/hr | 📅 67.6M today
```

设计原则：**前台零重活**——模型 / 上下文% / 5h 额度全部从 hook JSON 与 claude-hud 本地取
（渲染 ~0.1s）；ccusage 的慢活（`daily` 今日 token、`statusline` 燃烧速率，都要扫全量日志）
**后台异步刷新**写缓存（`flock` 防并发），状态栏只读缓存永不阻塞。无 Node 环境用 **bun** 跑
ccusage / claude-hud。

- `~/.claude/statusline.sh` — 合成脚本（`settings.json` 的 `statusLine` 指向它）
- `~/.claude/claude-hud/dist/` — claude-hud（手动接线，只取其上下文%）
- ccusage — bun 全局装，仅用 `daily` / `statusline`
- 完整安装步骤与脚本：`integrations/token-statusline/README.md`

额度段（`⏳`）与内置 `/usage` 同源（hook 的 `rate_limits`），仅订阅账号 + 较新 Claude Code 下发；
缺字段时自动省略。看准确额度进度用 `/usage`。

## 安装引导

当用户首次使用或询问如何安装时，按以下步骤引导：

### 1. MCP 依赖

检查 `mcp/siyuan/node_modules` / `mcp/notion/node_modules` 是否存在，不存在则按需执行：

```bash
cd mcp/siyuan && npm install    # 思源
cd mcp/notion && npm install    # Notion
```

再在仓库根建 `.mcp.json`（见上文 MCP 章节），只注册要用的那几个 server。

### 2. 配置文件

检查 `~/.navi/config.toml` 是否存在。不存在则创建，并询问用户填入以下配置：

```toml
[github]
token = "ghp_xxx"           # GitHub token，无需勾选任何 scope

[siyuan]
url = "http://127.0.0.1:6806"
token = "your-siyuan-api-token"

[notion]                              # MCP 读写 Notion 笔记
token       = "ntn_xxx"              # Internal Integration Secret
database_id = ""                      # 可选，create_page 的默认父级

[swanlab]
api_host = "http://host:port/api"   # SWANLAB_API_HOST，自建后端地址（云可留空）
web_host = "http://host:port"       # SWANLAB_WEB_HOST，前端地址（可留空）
api_key  = "your-swanlab-api-key"   # SWANLAB_API_KEY
username = ""                        # 默认 workspace（可选）
project  = ""                        # 默认项目（可选）

[zotero]                              # /navi-paper 同步论文用
api_key         = "your-zotero-key"  # Zotero Web API key（read 即可）
user_id         = "1234567"          # 数字 userID
webdav_url      = "https://host/dav/.../zotero/"  # 附件 WebDAV（以 zotero/ 结尾）
webdav_user     = "name"
webdav_password = "secret"

[paper]                               # /navi-paper 问答用
cache     = "~/.navi/paper-cache"    # PDF + 索引 + manifest 根目录
api_key   = "sk-..."                  # SiliconFlow key
base_url  = "https://api.siliconflow.cn/v1"
llm       = "deepseek-ai/DeepSeek-V3"
embedding = "Qwen/Qwen3-Embedding-8B"
```

如果用户不需要某项功能，对应配置可以跳过。`/navi-paper` 还需 `pip install -r .claude/skills/navi-paper/requirements.txt`。

### 3. Token 用量状态栏

按 `integrations/token-statusline/README.md` 装 bun + ccusage + claude-hud，把用量常驻状态栏
（模型 / 上下文 / 5h 额度 / 燃烧速率 / 今日 token）。只想要 claude-hud 官方版可直接
`/plugin marketplace add jarrodwatts/claude-hud` → `/plugin install claude-hud` → `/claude-hud:setup`。

### 4. tmux-claude-status（可选）

如果用户使用 tmux，执行：

```bash
bash integrations/tmux-claude-status/install.sh
```

## 配置

配置目录默认 `~/.navi/`，可用环境变量 **`NAVI_HOME`** 覆盖（所有 skill 脚本与 MCP server 统一走这个变量，未设置时回退默认，老行为不变）。要改到别处需**三处接线**，缺一处就会出现「命令行能跑、Claude 里报找不到配置」这类不一致：

| 接线点 | 作用范围 |
|--------|----------|
| `~/.bashrc` 里 `export NAVI_HOME=...` | 你手动敲命令时（注意 `bash -c` 非交互 shell 不读 bashrc）|
| `.claude/settings.json` 的 `env` | Claude Code 通过 Bash 工具跑 skill 脚本时 |
| `.mcp.json` 里各 server 的 `env` | MCP server 进程（思源 / Notion）|

```json
// .claude/settings.json（已被 gitignore）
{ "env": { "NAVI_HOME": "/your/config/dir" } }
```

配置文件位于 `$NAVI_HOME/config.toml`（默认 `~/.navi/config.toml`）：

```toml
[github]
token = "ghp_xxx"

[siyuan]
url = "http://127.0.0.1:6806"
token = "your-siyuan-api-token"

[notion]                              # MCP 读写 Notion 笔记
token       = "ntn_xxx"              # Internal Integration Secret
database_id = ""                      # 可选，create_page 的默认父级

[swanlab]
api_host = "http://host:port/api"   # SWANLAB_API_HOST（云可留空）
web_host = "http://host:port"       # SWANLAB_WEB_HOST（可留空）
api_key  = "your-swanlab-api-key"   # SWANLAB_API_KEY
username = ""                        # 默认 workspace（可选）
project  = ""                        # 默认项目（可选）

[zotero]
api_key         = "your-zotero-key"
user_id         = "1234567"
webdav_url      = "https://host/dav/.../zotero/"
webdav_user     = "name"
webdav_password = "secret"

[paper]
cache     = "~/.navi/paper-cache"
api_key   = "sk-..."                  # SiliconFlow key
base_url  = "https://api.siliconflow.cn/v1"
llm       = "deepseek-ai/DeepSeek-V3"
embedding = "Qwen/Qwen3-Embedding-8B"
```

## 输出规范

- 默认用中文输出
- 论文标题、作者等保留英文原文
- 摘要翻译为中文
