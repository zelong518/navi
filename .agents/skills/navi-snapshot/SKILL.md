---
name: navi-snapshot
description: 把本地 Claude Code 与 Codex 的完整工作状态（配置 + 会话 + 凭证 + 插件）快照到持久目录，重启/换机后一条命令恢复
argument-hint: "upload [名字] | sync [名字=latest] | list | prune [N=10]"
user-invocable: true
allowed-tools: Bash, Read
---

# Claude Code / Codex 状态快照

**为什么需要**：开发机的 home 往往不是持久存储，重启后 `~/.claude` 与 `~/.codex`
被清空——登录态、会话记录、装好的插件全没了。而 `/volume` 这类挂载是持久的。
本 skill 把两个工具的**完整工作状态**存到持久目录，重启后一条 `restore` 复活。

**触发**：
- `/navi-snapshot upload [名字]` —— 存一份快照（省略名字用时间戳）
- `/navi-snapshot sync [名字]` —— 恢复（省略名字用 latest）
- `/navi-snapshot list` —— 看有哪些快照
- `/navi-snapshot prune [N]` —— 只留最近 N 份时间戳快照
- 用户说「快照一下 claude」「重启前存一下」「恢复上次的 claude 状态」等

> **脚本路径约定**：下面的 `$S` 指**本 skill 的 base directory**（调用时会给出绝对路径）。
> 先 `S="<base directory>"` 再拼命令，**不要**用相对 cwd 的 `.claude/skills/...`——
> navi 的 skill 可以在任何仓库里被调用，那时 cwd 不是 navi 仓库根。

## 用法

```bash
S="<base directory>/snapshot.py"        # 调用时给出的绝对路径

# upload —— 存快照
python3 $S upload                    # 存成 snapshot-<时间戳>，并更新 latest
python3 $S upload 重启前              # 命名槽位 snapshot-重启前；再 upload 同名 = 更新它
python3 $S upload --archive          # 打成单个 tar.gz，便于搬走
python3 $S upload --keep 24          # 顺手只保留最近 24 份时间戳快照
python3 $S upload --project .        # 额外收当前项目的 .claude/.codex/.agents
python3 $S upload --dest /other/dir  # 指定目录（优先于配置）

# sync —— 从快照恢复
python3 $S sync --dry-run            # 用 latest，先看会动哪些文件（建议先跑）
python3 $S sync                      # 用 latest 真恢复
python3 $S sync 重启前                # 指定命名槽位（snapshot- 前缀可省）
python3 $S sync snapshot-20260819-155806   # 指定时间戳快照
python3 $S sync /path/to/x.tar.gz    # 从归档恢复，自动解压
python3 $S sync latest --project-dest DIR  # 连项目级定制一起还原

python3 $S list                      # 列快照：时间/主机/文件数/版本/包含内容
python3 $S prune 10                  # 只留最近 10 份时间戳快照（命名槽位不动）
```

`save` / `restore` / `ls` 是 `upload` / `sync` / `list` 的兼容别名。

**快照引用怎么解析**（`sync` 的位置参数）：省略 = `latest` → 直接路径 → `<目录>/<名字>`
→ `<目录>/snapshot-<名字>` → 同名 `.tar.gz`。都找不到时报错并列出可用快照。

**命名槽位 vs 时间戳快照**：`upload <名字>` 建的是槽位，重复 upload 会**原子替换**
（先写临时目录，成功才换上去，中途失败不破坏已有快照），且**永不被 `prune`/`keep` 自动删**；
不给名字的是时间戳快照，参与滚动清理。

## 收什么、不收什么

| 类别 | 默认 | 内容 |
|------|------|------|
| 配置 | ✅ | `settings.json` / `CLAUDE.md` / `agents` / `skills` / `commands` / `hooks` / `keybindings` / `statusline.sh` / `~/.claude.json`；Codex 的 `config.toml` / `AGENTS.md` / `prompts` / `skills` / `installation_id` |
| 会话 | ✅ | Claude：`projects`（会话记录）/ `sessions` / `history.jsonl` / `todos` / `file-history` / `shell-snapshots`（支撑 `/rewind`）；Codex：`state_*.sqlite`（会话）/ `memories_*.sqlite`（记忆）/ `goals_*.sqlite` / `logs_*.sqlite` / `shell_snapshots` |
| 凭证 | ✅ | `.credentials.json` / `auth.json` —— 不收的话每次重启都要重新登录 |
| 插件 | ✅ | `plugins/`（数 MB）—— 不收的话重启后要重装 |
| 运行时垃圾 | ❌ | `cache/` / `ide/` / `backups/` / `tmp/` / `models_cache.json` 等重建即可的东西 |

Codex 的会话与记忆存在带版本号的 sqlite 里（`state_5.sqlite` 这种），白名单用 glob 匹配，
并走 **sqlite backup API** 取一致快照——直接 `cp` 遇上 WAL 可能拷到撕裂状态。

瘦身开关：`--no-history` / `--no-credentials` / `--no-plugins`（只对 `upload` 有效）。

## 安全

快照**含明文凭证**，所以脚本会把快照目录设 `700`、凭证副本设 `600`。
放到别人能读的位置时务必加 `--no-credentials`。
`snapshots/` 已排除在 `navi sync` 之外，不会被上传到 WebDAV。

## 编排要求

1. **`sync` 前默认先跑 `--dry-run`** 给用户看会动哪些文件，确认后再真恢复。
   用户明确说「直接恢复」时可跳过。
2. `sync` 会校验每个文件的 md5（存在 manifest 里），不符则中止——**不要**
   随手加 `--force` 绕过，先跟用户确认快照是否损坏。
3. 被覆盖的原文件自动备份到 `~/.navi-pre-restore-<时间戳>/`，恢复后把这个路径告诉用户。
4. 恢复是**合并式**的：只写回快照里有的文件，不删本地多出来的。要完全一致得自己先清空目标目录。
5. **恢复后需要重启 Claude Code** 才会加载回来的配置与会话。
6. 用户没指定目录时用配置 `[snapshot].dest`；配置也没有则落 `$NAVI_HOME/snapshots`，
   此时提醒用户确认这个位置是否在持久存储上。

## 配置

`$NAVI_HOME/config.toml` 的 `[snapshot]` 段（可选）：

```toml
[snapshot]
dest = "/volume/.../snapshots"   # 快照目录，必须在持久存储上
keep = 10                         # 保留最近 N 份，超出自动删（不填不删）
```

## 定时快照

挂 cron 每小时存一份、只留最近 24 份，重启后最多丢 1 小时：

```cron
0 * * * * cd /path/to/navi && NAVI_HOME=/your/config python3 "$S/snapshot.py" upload --keep 24 >> /tmp/navi-snapshot.log 2>&1
```
