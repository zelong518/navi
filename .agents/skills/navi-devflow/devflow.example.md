# devflow —— 各仓库的地址与身份（模板）

复制成 `$NAVI_HOME/devflow.md` 再填。**这份文件不进仓库**，
因为它含内部 host、项目路径与身份信息。`navi-devflow` skill 会在需要时读它。

Token **不要写在这里**，只记「从哪拿、要什么 scope」。

## 仓库：<别名>

| 项 | 值 |
|---|---|
| 平台 | GitLab / GitHub / … |
| host | `git.example.com` |
| 项目 | `<group>/<project>` |
| remote 约定 | 上游 = `origin`，内部 = `gitlab` |
| 本地路径 | `/path/to/repo` |
| git 身份 | `git config --local user.name "..."` / `user.email "..."` |
| 主干分支 | `main` |
| AI 署名 | **禁止** / 允许 |
| token 来源 | 用户会话提供；需要 `api` scope（只有 read/write_repository 不能建 issue/MR）|

API 模板（token 走环境变量）：

```bash
T='<token>'; H='https://git.example.com/api/v4'; P='<group>%2F<project>'
curl -s --header "PRIVATE-TOKEN: $T" "$H/user"          # 先验 scope
curl -s -X POST --header "PRIVATE-TOKEN: $T" "$H/projects/$P/merge_requests" \
  --data-urlencode "source_branch=fix/xxx" --data-urlencode "target_branch=main" \
  --data-urlencode "title=fix(scope): ..." --data-urlencode "description@mr.md" \
  --data-urlencode "remove_source_branch=true"
```

## 本仓库特有的构建注意事项

- 子模块要先 checkout 吗？
- 构建后有什么会被 `make clean` 掉、需要手动重建？
- 环境怎么激活（conda / venv 路径）？
- ⚠️ 装在共享文件系统上时，一台机器 `pip install -e .` 会影响所有机器吗？
