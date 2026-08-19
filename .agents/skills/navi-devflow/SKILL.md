---
name: navi-devflow
description: 提 issue、开 MR/PR、写 commit、准备合并时使用——一套让别人不依赖你的环境也能复现和判断的协作规范：issue 五段（含用矩阵表呈现单变量对照）、MR 五段（What / Why it broke / Changes / How verified / Risk）、conventional commit、分支命名、以及合并前的验证门禁。仓库地址与 token 读 $NAVI_HOME/devflow.md。触发词："提 issue"、"开 MR"、"merge request"、"提 PR"、"合并"、"commit 信息"、"code review"、"要不要能合了"。
argument-hint: "[issue|mr|commit|gate=全部] [仓库别名]"
user-invocable: true
allowed-tools: Bash, Read, Write
---

# 开发协作流程规范

**流程**，与具体仓库无关。核心目标一句话：

> **让别人不依赖你的环境，也能复现你的结论并做出判断。**

各仓库的 host / 项目路径 / git 身份 / token 获取方式**不在本仓库**，
读 `$NAVI_HOME/devflow.md`（不存在则参考同目录 `devflow.example.md` 自建）。
性能类改动的测量方法见 `navi-perf-discipline` skill。

## 参数

`$ARGUMENTS` 可选：

| 参数 | 默认 | 说明 |
|------|------|------|
| 章节 | 全部 | `issue` / `mr` / `commit` / `gate`，只讲这一段 |
| 仓库别名 | 无 | 给了就先从 `$NAVI_HOME/devflow.md` 取该仓库的 host / 身份 / 是否禁 AI 署名 |

## Token 先验 scope，再动手

只有仓库读写权限的 token **能 push 但不能建 issue/MR**。先打一次 `/user`
之类的接口确认，403 `insufficient_scope` 就是 scope 不够——
**不要等写完长长的 MR 描述才发现提不上去。**

Token 一律**用环境变量传，绝不写进文件或提交**。用户在会话里给的 token 不落盘。

## Commit 规范

- **Conventional Commits**：`<type>(<scope>): <祈使句摘要>`，
  类型 `feat`/`fix`/`perf`/`refactor`/`docs`/`chore`，scope 用模块名，摘要 ≤ 72 字符
- **正文写清楚：现象 → 根因（带数据）→ 改法 → 验证结果**。
  性能类必须带前后数字**和测量条件**（机器、文件系统、数据量、并发、轮数）
- **一个 commit 只做一件事**：修复、重构、性能优化分开提
- ⚠️ **AI 署名（`Co-Authored-By` 等）按仓库约定**——有仓库明确禁止，
  提交前查 `$NAVI_HOME/devflow.md` 里该仓库的条目

## 分支

- **不直接往主干提交**，每个子功能一个分支走 MR/PR 合入
- 命名 `fix/<kebab-slug>`、`feat/<kebab-slug>`、`perf/<kebab-slug>`；
  从 issue 出发时把编号写进去：`fix/issue-1-uring-enomem`
- 大工作用一个**集成分支**，子功能分支各自开 MR 合进去，便于逐项验证和回退

## Issue 怎么写（五段）

1. **Summary** —— 一句话说清坏在哪，**以及影响面**（是否影响默认路径）
2. **Reproduce** —— 机器/内核/文件系统/规模 + **最小复现代码** + 原始报错日志
3. **Root cause** —— **用矩阵表格呈现单变量对照实验**，并说明是**在被测库之外**独立复现的
4. **Impact** —— 谁会踩到、失败模式有多严重（能 fallback 还是直接 abort）
5. **Suggested fix** —— 方向 + 预期收益数字

特别要写清**为什么这个坑不好防**（例如「注册成功≠能用」「小 IO 探测会误判为可用」）——
这决定了修法的形状。

## MR / PR 怎么写（五段，缺一不可）

- **What** —— 改了什么，为什么这事重要（影响默认路径吗？）
- **Why it broke** —— 根因，**带对照数据表**
- **Changes** —— 逐个文件/函数说明**改动意图**，不是罗列 diff
- **How verified** —— 机器、数据量、前后数字；
  **必须包含「没有把别的路径改坏」的回归证据**
- **Risk** —— 什么情况下这个改动是次优的，以及**怎么退回**（env 开关/ revert 路径）

描述里写 `Closes #N` 关联 issue。

## 合并前门禁

按顺序过，前面的比后面的便宜：

1. **自审 diff**（`/code-review`），把真问题都修掉再交给人
2. **编译通过**
3. ⚠️ **重装后再实测**：`build_ext` 之类的增量构建**不会更新已被 import 的动态库**，
   不重装就是在测旧代码
4. **性能改动**：交错 A/B 至少 3 轮取中位数，**并复测其他配置确认无回归**
5. **行为/数值改动**：跑正确性对比（同输入 + 确定性解码，改动前 vs 后）

## 编排要求

1. 开 MR/PR 前**先确认五段都有实料**；`How verified` 只写「跑通了」等于没写。
2. 性能数字必须带测量条件与轮数，单次最好值不算证据（见 `perf-discipline`）。
3. Token 从用户输入或环境变量取，**不写入任何文件、不出现在 commit 里**。
4. 提交前查该仓库是否禁止 AI 署名。
5. 不确定仓库地址/身份时读 `$NAVI_HOME/devflow.md`，**不要猜**。
