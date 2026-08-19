#!/usr/bin/env python3
"""snapshot.py — 把本地 Claude Code 与 Codex 的「配置与定制」做成快照。

场景：开发机的 home 不是持久存储，重启后 ~/.claude 与 ~/.codex 全部清空，
而 /volume 是持久盘。所以本工具默认做**全量快照**（配置 + 会话 + 凭证 + 插件），
重启后一条 restore 就能回到原来的工作状态，不用重新登录、不用重装插件。

原理：白名单拷贝 + manifest 记录每文件 md5。只有纯运行时缓存（cache/、ide/、
tmp/ 之类重建即可的东西）不收。Codex 把会话/记忆存在 sqlite 里（state_*.sqlite
这类带版本号的文件），用 sqlite 的 backup API 取一致快照，避免 WAL 撕裂。

用法：
    python3 snapshot.py save --dest /path/to/dir          # 存一份快照（配置 + 会话）
    python3 snapshot.py save --dest DIR --tag 换机前       # 带标签便于识别
    python3 snapshot.py save --dest DIR --archive         # 打成单个 tar.gz
    python3 snapshot.py save --dest DIR --project .       # 额外收当前项目的 .claude/.codex
    python3 snapshot.py list --dest DIR                   # 列已有快照（含各自包含的内容）
    python3 snapshot.py restore DIR/<快照名> --dry-run     # 先看会动哪些文件
    python3 snapshot.py restore DIR/<快照名>               # 恢复（覆盖前自动备份现有文件）

目标目录优先级：--dest > 配置 [snapshot].dest > $NAVI_HOME/snapshots

瘦身开关（默认全收）：
    --no-history      不收会话记录（projects / sessions / history.jsonl 等）
    --no-credentials  不收凭证。凭证是**明文** token，快照目录会被 chmod 700、
                      凭证文件 600；快照放在别人能读到的地方时务必加这个开关
    --no-plugins      不收已安装插件目录（数 MB）

恢复语义：按 manifest 逐文件写回，先校验 md5（不符则中止，除非 --force），
被覆盖的原文件先备份到 ~/.navi-pre-restore-<时间戳>/。是**合并式**恢复——
只写回快照里有的文件，不会删除本地多出来的文件。

配置：$NAVI_HOME/config.toml 的 [snapshot] 段（可选）：
    [snapshot]
    dest = "/path/to/snapshots"   # --dest 未传时用
    keep = 10                      # 保留最近 N 份，超出的自动删（不填不删）
"""

import argparse
import hashlib
import re
import json
import os
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # py<3.11
    import tomli as tomllib  # type: ignore

# 配置目录：环境变量 NAVI_HOME 优先，未设置则默认 ~/.navi
NAVI_HOME = Path(os.environ.get("NAVI_HOME") or "~/.navi").expanduser()
CONFIG_PATH = NAVI_HOME / "config.toml"
HOME = Path.home()

# 拷贝时永不带走的垃圾
IGNORE = shutil.ignore_patterns("node_modules", "__pycache__", "*.pyc", ".git", "*.lock")
# plugins/ 里是 marketplace 的 git clone，剥掉 .git 会让后续更新失效，只滤依赖目录
IGNORE_KEEP_GIT = shutil.ignore_patterns("node_modules", "__pycache__", "*.pyc")

# ---- 白名单：只收配置与定制 ----
CLAUDE_ROOT = HOME / ".claude"
CLAUDE_ITEMS = [
    "settings.json", "settings.local.json", "keybindings.json", "CLAUDE.md",
    "agents", "skills", "commands", "hooks", "output-styles", "workflows",
    "statusline.sh", "plugins/config.json", "plugins/known_marketplaces.json",
]
CLAUDE_OPTIONAL = {
    # history 默认开：projects 是会话记录，file-history / shell-snapshots 支撑 /rewind
    "history": ["history.jsonl", "projects", "sessions", "todos",
                "file-history", "shell-snapshots", "session-env"],
    "credentials": [".credentials.json"],
    "plugins": ["plugins"],
}
# ~/.claude.json：项目清单 + MCP server 声明，是配置，默认收
CLAUDE_TOPLEVEL = [".claude.json"]

CODEX_ROOT = HOME / ".codex"
CODEX_ITEMS = ["config.toml", "AGENTS.md", "agents", "prompts", "skills",
               "config.json", "installation_id", ".personality_migration"]
CODEX_OPTIONAL = {
    # Codex 把会话/记忆/目标存在带版本号的 sqlite 里（state_5.sqlite 这种），
    # 不是 jsonl；用 glob 匹配版本号。-wal/-shm 不单独收，sqlite backup 会合并进主库。
    "history": ["state_*.sqlite", "memories_*.sqlite", "goals_*.sqlite", "logs_*.sqlite",
                "shell_snapshots", "sessions", "history.jsonl", "log"],
    "credentials": ["auth.json"],
    "plugins": ["plugins"],
}

# --project 时额外收的项目级定制
PROJECT_ITEMS = [".claude", ".codex", ".agents", ".mcp.json", "CLAUDE.md", "AGENTS.md"]


def load_cfg() -> dict:
    """读 [snapshot]：dest（可选）、keep（可选）。配置不存在也不报错。"""
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH, "rb") as f:
        return tomllib.load(f).get("snapshot") or {}


def tool_version(cmd: str) -> str | None:
    """取 CLI 版本号，没装就返回 None。"""
    if not shutil.which(cmd):
        return None
    try:
        r = subprocess.run([cmd, "--version"], capture_output=True, text=True, timeout=15)
        return (r.stdout or r.stderr).strip().splitlines()[0] if r.returncode == 0 else None
    except (subprocess.SubprocessError, OSError, IndexError):
        return None


def md5_of(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_sqlite(src: Path, dst: Path) -> bool:
    """用 sqlite backup API 拷一份一致的库（把 WAL 合并进去）。失败回 False 让调用方降级。"""
    try:
        import sqlite3
        dst.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
        try:
            out = sqlite3.connect(dst)
            try:
                with out:
                    con.backup(out)
            finally:
                out.close()
        finally:
            con.close()
        return True
    except Exception:
        for junk in (dst, Path(str(dst) + "-wal"), Path(str(dst) + "-shm")):
            if junk.exists():
                junk.unlink()
        return False


def copy_item(src: Path, dst: Path, keep_git: bool = False) -> int:
    """拷一个文件或整棵目录，返回拷到的文件数。父目录按需创建。"""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_file() and src.suffix in (".sqlite", ".db") and copy_sqlite(src, dst):
        return 1   # sqlite 走 backup API，成功即完事
    if src.is_dir():
        shutil.copytree(src, dst, ignore=IGNORE_KEEP_GIT if keep_git else IGNORE,
                        dirs_exist_ok=True, symlinks=True)
        return sum(1 for p in dst.rglob("*") if p.is_file())
    shutil.copy2(src, dst)
    if "credential" in src.name or src.name == "auth.json":
        os.chmod(dst, 0o600)   # 凭证副本不给别人读
    return 1


def wanted_items(base_items: list, optional: dict, flags: dict) -> list:
    """白名单 + 被开关打开的可选项。"""
    items = list(base_items)
    for key, extra in optional.items():
        if flags.get(key):
            items += [e for e in extra if e not in items]
    return items


def collect(root: Path, items: list, out: Path, prefix: str) -> tuple[list, list]:
    """把 root 下的 items 拷到 out/prefix。回 (已收清单, 缺失清单)。"""
    got, missing = [], []
    for rel in items:
        if "*" in rel:   # glob 项：展开成实际文件名，一个都没匹配上才算缺失
            hits = sorted(root.glob(rel))
            if not hits:
                missing.append(rel)
            for h in hits:
                r = h.relative_to(root).as_posix()
                got.append({"path": f"{prefix}/{r}",
                            "files": copy_item(h, out / prefix / r),
                            "kind": "dir" if h.is_dir() else "file"})
            continue
        src = root / rel
        if not src.exists():
            missing.append(rel)
            continue
        n = copy_item(src, out / prefix / rel, keep_git=rel.startswith("plugins"))
        got.append({"path": f"{prefix}/{rel}", "files": n,
                    "kind": "dir" if src.is_dir() else "file"})
    return got, missing


def do_save(args, cfg) -> int:
    dest = Path(args.dest or cfg.get("dest") or (NAVI_HOME / "snapshots")).expanduser()
    dest.mkdir(parents=True, exist_ok=True)

    flags = {"history": not args.no_history,
             "credentials": not args.no_credentials,
             "plugins": not args.no_plugins}

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    slot = getattr(args, "name", None)
    if slot:
        # 命名槽位：snapshot-<名字>，重复 upload 同名 = 更新这个槽位
        name = slot if slot.startswith("snapshot-") else f"snapshot-{slot}"
    else:
        name = f"snapshot-{stamp}" + (f"-{args.tag}" if args.tag else "")
    final_path = dest / name
    replacing = final_path.exists()
    # 先建到临时名，成功后再换上去——中途失败不会破坏已有快照
    work = dest / f".{name}.new-{stamp}"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    os.chmod(work, 0o700)   # 可能含凭证，别让同机其他用户读

    manifest = {
        "created": datetime.now().astimezone().isoformat(timespec="seconds"),
        "host": socket.gethostname(),
        "user": os.environ.get("USER") or os.environ.get("LOGNAME") or "",
        "navi_home": str(NAVI_HOME),
        "options": flags,
        "versions": {"claude": tool_version("claude"), "codex": tool_version("codex")},
        "sources": {}, "collected": [], "missing": {},
    }

    # Claude Code
    if CLAUDE_ROOT.exists():
        manifest["sources"]["claude"] = str(CLAUDE_ROOT)
        got, miss = collect(CLAUDE_ROOT, wanted_items(CLAUDE_ITEMS, CLAUDE_OPTIONAL, flags),
                            work, "claude")
        manifest["collected"] += got
        manifest["missing"]["claude"] = miss
        for rel in CLAUDE_TOPLEVEL:
            src = HOME / rel
            if src.exists():
                copy_item(src, work / "home" / rel)
                manifest["collected"].append({"path": f"home/{rel}", "files": 1, "kind": "file"})
    else:
        manifest["sources"]["claude"] = None

    # Codex
    if CODEX_ROOT.exists():
        manifest["sources"]["codex"] = str(CODEX_ROOT)
        got, miss = collect(CODEX_ROOT, wanted_items(CODEX_ITEMS, CODEX_OPTIONAL, flags),
                            work, "codex")
        manifest["collected"] += got
        manifest["missing"]["codex"] = miss
    else:
        manifest["sources"]["codex"] = None

    # 可选：项目级定制
    if args.project:
        proj = Path(args.project).expanduser().resolve()
        manifest["sources"]["project"] = str(proj)
        got, miss = collect(proj, PROJECT_ITEMS, work, f"project/{proj.name}")
        manifest["collected"] += got
        manifest["missing"]["project"] = miss

    # 逐文件 md5，供 restore 校验
    files = []
    for p in sorted(work.rglob("*")):
        if p.is_symlink():
            # 软链只记指向，不跟随——指向目录的软链不是 file，早先漏记导致 restore 不会重建它
            files.append({"path": str(p.relative_to(work)), "symlink": os.readlink(p)})
        elif p.is_file():
            files.append({"path": str(p.relative_to(work)), "size": p.stat().st_size,
                          "md5": md5_of(p)})
    total = sum(f.get("size", 0) for f in files)
    manifest["files"] = files
    manifest["totals"] = {"files": len(files), "bytes": total}
    (work / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.archive:
        tgz = dest / f"{name}.tar.gz"
        replacing = tgz.exists()
        with tarfile.open(work.parent / f".{name}.new-{stamp}.tar.gz", "w:gz") as tar:
            tar.add(work, arcname=name)
        shutil.rmtree(work)
        if replacing:
            tgz.unlink()
        (work.parent / f".{name}.new-{stamp}.tar.gz").rename(tgz)
        final = tgz
    else:
        old = None
        if replacing:
            old = dest / f".{name}.old-{stamp}"
            final_path.rename(old)
        work.rename(final_path)
        if old:
            shutil.rmtree(old, ignore_errors=True)
        final = final_path

    # latest 软链（失败不致命，有些后端不支持软链）
    link = dest / "latest"
    try:
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(final.name)
    except OSError:
        pass

    print(f"{'♻️  已更新同名快照' if replacing else '✅ 快照已保存'}：{final}")
    print(f"   Claude Code: {manifest['sources']['claude'] or '未找到'}"
          f"{'  ' + manifest['versions']['claude'] if manifest['versions']['claude'] else ''}")
    print(f"   Codex:       {manifest['sources']['codex'] or '未找到'}"
          f"{'  ' + manifest['versions']['codex'] if manifest['versions']['codex'] else ''}")
    print(f"   共 {len(files)} 个文件 / {total / 1024:.1f} KB")
    included = [k for k, v in flags.items() if v]
    skipped = [k for k, v in flags.items() if not v]
    print(f"   含：配置" + (f" + {', '.join(included)}" if included else ""))
    if skipped:
        print(f"   未含：{', '.join(skipped)}"
              + ("（恢复到新机器需重新登录）" if "credentials" in skipped else ""))
    prune(dest, args.keep if args.keep is not None else cfg.get("keep"))
    return 0


def snapshots_in(dest: Path) -> list:
    """按名字（含时间戳）排序的快照列表。"""
    out = []
    for p in dest.iterdir():
        if p.name == "latest":
            continue
        if p.is_dir() and (p / "manifest.json").exists():
            out.append(p)
        elif p.is_file() and p.name.startswith("snapshot-") and p.name.endswith(".tar.gz"):
            out.append(p)
    return sorted(out, key=lambda p: p.name)


TS_NAME = re.compile(r"^snapshot-\d{8}-\d{6}")


def prune(dest: Path, keep) -> None:
    """只滚动清理时间戳快照；命名槽位（upload <名字>）是用户显式建的，永不自动删。"""
    if not keep:
        return
    snaps = [p for p in snapshots_in(dest) if TS_NAME.match(p.name)]
    for old in snaps[: max(0, len(snaps) - int(keep))]:
        shutil.rmtree(old) if old.is_dir() else old.unlink()
        print(f"   已清理旧快照：{old.name}")
    fix_latest(dest)   # 被清掉的可能正是 latest 的目标


def read_manifest(snap: Path) -> dict:
    """目录直接读，tar.gz 则解到临时目录再读。"""
    if snap.is_dir():
        return json.loads((snap / "manifest.json").read_text(encoding="utf-8"))
    with tarfile.open(snap) as tar:
        for m in tar.getmembers():
            if m.name.endswith("/manifest.json"):
                f = tar.extractfile(m)
                return json.loads(f.read().decode("utf-8"))
    raise SystemExit(f"{snap} 里没有 manifest.json")


def do_list(args, cfg) -> int:
    dest = Path(args.dest or cfg.get("dest") or (NAVI_HOME / "snapshots")).expanduser()
    if not dest.exists():
        raise SystemExit(f"目录不存在：{dest}")
    snaps = snapshots_in(dest)
    if not snaps:
        print(f"{dest} 下没有快照。")
        return 0
    print(f"{dest}（{len(snaps)} 份）\n")
    for p in snaps:
        try:
            m = read_manifest(p)
        except Exception as e:  # 坏快照也要列出来，别让一份坏的挡住全部
            print(f"- {p.name}  ⚠️ manifest 读取失败: {e}")
            continue
        opts = [k for k, v in (m.get("options") or {}).items() if v]
        print(f"- {p.name}{'  [tar.gz]' if p.is_file() else ''}")
        print(f"    {m.get('created','?')}  @{m.get('host','?')}  "
              f"{m.get('totals',{}).get('files','?')} 文件 / "
              f"{m.get('totals',{}).get('bytes',0)/1024:.1f} KB")
        v = m.get("versions") or {}
        print(f"    claude={v.get('claude') or '-'}  codex={v.get('codex') or '-'}"
              + (f"  含: {', '.join(opts)}" if opts else ""))
    return 0


# restore 时快照内目录 → 本地目标
TARGETS = {"claude": CLAUDE_ROOT, "codex": CODEX_ROOT, "home": HOME}


def newest(dest: Path) -> Path | None:
    """按 manifest 的创建时间取最新一份（拿不到就退回 mtime）。"""
    snaps = snapshots_in(dest)
    if not snaps:
        return None
    def key(p: Path):
        try:
            return read_manifest(p).get("created", "")
        except Exception:
            return ""
    return max(snaps, key=lambda p: (key(p), p.stat().st_mtime))


def fix_latest(dest: Path) -> None:
    """latest 悬空（目标被删）时重新指向最新一份；没有快照就把软链去掉。"""
    link = dest / "latest"
    if link.is_symlink() and not link.exists():   # 悬空
        link.unlink()
    if link.exists():
        return
    n = newest(dest)
    if n:
        try:
            link.symlink_to(n.name)
        except OSError:
            pass


def resolve_ref(dest: Path, ref: str | None) -> Path:
    """把用户给的引用解析成快照路径：省略 = latest，可以是名字、snapshot-名字、或直接路径。"""
    ref = (ref or "latest").strip()
    if ref == "latest":
        fix_latest(dest)                          # 悬空自动修
        link = dest / "latest"
        if not link.exists():
            n = newest(dest)
            if n is None:
                raise SystemExit(f"{dest} 下还没有快照，先跑 upload。")
            print(f"（没有可用的 latest，回退到最新一份：{n.name}）")
            return n
        return link
    direct = Path(ref).expanduser()
    if direct.exists():
        return direct
    for cand in (dest / ref, dest / f"snapshot-{ref}",
                 dest / f"{ref}.tar.gz", dest / f"snapshot-{ref}.tar.gz"):
        if cand.exists():
            return cand
    avail = [p.name for p in snapshots_in(dest)] if dest.exists() else []
    raise SystemExit(
        f"找不到快照 {ref!r}（在 {dest} 下）。"
        + (f"\n可用：{', '.join(avail)}" if avail else "\n该目录下还没有快照，先跑 upload。"))


def do_restore(args, cfg) -> int:
    dest = Path(args.dest or cfg.get("dest") or (NAVI_HOME / "snapshots")).expanduser()
    snap = resolve_ref(dest, getattr(args, "snapshot", None))

    tmp = None
    root = snap
    if snap.is_file():
        tmp = tempfile.mkdtemp(prefix="navi-snapshot-")
        with tarfile.open(snap) as tar:
            tar.extractall(tmp)
        root = next(Path(tmp).iterdir())

    manifest = read_manifest(snap)
    plan, unknown = [], []
    for entry in manifest.get("files", []):
        rel = Path(entry["path"])
        if rel.name == "manifest.json":
            continue
        top = rel.parts[0]
        if top == "project":
            if not args.project_dest:
                continue  # 默认不回写，避免踩当前工作区
            plan.append((root / rel,
                         Path(args.project_dest).expanduser() / Path(*rel.parts[2:]), entry))
            continue
        if top not in TARGETS:
            unknown.append(str(rel))
            continue
        plan.append((root / rel, TARGETS[top] / Path(*rel.parts[1:]), entry))

    print(f"快照：{snap}")
    print(f"创建于 {manifest.get('created')} @{manifest.get('host')}")
    print(f"将恢复 {len(plan)} 个文件"
          + (f"（跳过 {len(unknown)} 个无法映射的）" if unknown else ""))
    has_proj = any(e["path"].startswith("project/") for e in manifest.get("files", []))
    if has_proj and not args.project_dest:
        print("注意：快照含 project/ 项目级定制，默认不回写；要还原加 --project-dest DIR。")
    if not (manifest.get("options") or {}).get("credentials"):
        print("注意：快照不含凭证，恢复后可能需要重新登录（claude / codex）。")

    bad = [str(src) for src, _, e in plan
           if "symlink" not in e and src.exists() and not src.is_symlink()
           and md5_of(src) != e["md5"]]
    if bad:
        print(f"⚠️ {len(bad)} 个文件 md5 与 manifest 不符，快照可能损坏：")
        for b in bad[:5]:
            print(f"   {b}")
        if not args.force:
            raise SystemExit("已中止。确认无误可加 --force。")

    if args.dry_run:
        for src, dst, e in plan:
            mark = "覆盖" if (dst.exists() or dst.is_symlink()) else "新建"
            kind = f" → {e['symlink']}" if "symlink" in e else ""
            print(f"  [{mark}] {dst}{kind}")
        print("\n（--dry-run，未做任何改动）")
        return 0

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = HOME / f".navi-pre-restore-{stamp}"
    restored = overwritten = 0
    for src, dst, e in plan:
        if dst.is_symlink() or dst.exists():
            b = backup / dst.relative_to(HOME)
            b.parent.mkdir(parents=True, exist_ok=True)
            if dst.is_symlink():
                b.symlink_to(os.readlink(dst))
                dst.unlink()
            else:
                shutil.copy2(dst, b)
            overwritten += 1
        dst.parent.mkdir(parents=True, exist_ok=True)
        if "symlink" in e:
            if dst.is_symlink() or dst.exists():
                dst.unlink()
            os.symlink(e["symlink"], dst)
        else:
            shutil.copy2(src, dst)
        restored += 1

    if tmp:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"✅ 已恢复 {restored} 个文件")
    if overwritten:
        print(f"   被覆盖的 {overwritten} 个已备份到 {backup}")
    return 0


def parse_args():
    ap = argparse.ArgumentParser(description="Claude Code / Codex 状态快照")
    sub = ap.add_subparsers(dest="cmd", required=True)

    # upload —— 存快照（save 为兼容别名）
    u = sub.add_parser("upload", aliases=["save"], help="把当前状态存成快照（默认带时间戳）")
    u.add_argument("name", nargs="?",
                   help="命名槽位：存成 snapshot-<名字>，重复 upload 同名即更新它；省略则用时间戳")
    u.add_argument("--dest", help="快照目录（默认取配置 [snapshot].dest）")
    u.add_argument("--tag", help="给时间戳快照加后缀（与位置参数互斥用法：snapshot-<时间戳>-<tag>）")
    u.add_argument("--project", help="额外收该项目目录下的 .claude/.codex/.agents 等")
    u.add_argument("--archive", action="store_true", help="打成单个 tar.gz")
    u.add_argument("--keep", type=int, help="只保留最近 N 份时间戳快照（命名槽位不受影响）")
    u.add_argument("--no-history", action="store_true",
                   help="不收会话记录（默认会收 projects / sessions / sqlite 等）")
    u.add_argument("--no-credentials", action="store_true",
                   help="不收凭证（默认会收，否则重启后要重新登录）")
    u.add_argument("--no-plugins", action="store_true",
                   help="不收已安装插件目录（默认会收，否则重启后要重装）")
    u.set_defaults(func=do_save)

    # sync —— 从快照恢复（restore 为兼容别名）
    y = sub.add_parser("sync", aliases=["restore"], help="从快照恢复到本地（默认用 latest）")
    y.add_argument("snapshot", nargs="?", default="latest",
                   help="快照引用：省略=latest，可给名字 / snapshot-名字 / 直接路径 / tar.gz")
    y.add_argument("--dest", help="快照目录（默认取配置 [snapshot].dest）")
    y.add_argument("--dry-run", action="store_true", help="只打印会动哪些文件，不改动")
    y.add_argument("--force", action="store_true", help="md5 校验不符也继续（慎用）")
    y.add_argument("--project-dest", help="把快照里的 project/ 内容还原到该目录（默认不还原）")
    y.set_defaults(func=do_restore)

    l = sub.add_parser("list", aliases=["ls"], help="列出已有快照")
    l.add_argument("--dest", help="快照目录（默认取配置 [snapshot].dest）")
    l.set_defaults(func=do_list)

    pr = sub.add_parser("prune", help="只保留最近 N 份时间戳快照（命名槽位不动）")
    pr.add_argument("keep", nargs="?", type=int, default=10, help="保留份数，默认 10")
    pr.add_argument("--dest", help="快照目录（默认取配置 [snapshot].dest）")
    pr.set_defaults(func=do_prune)

    return ap.parse_args()


def do_prune(args, cfg) -> int:
    dest = Path(args.dest or cfg.get("dest") or (NAVI_HOME / "snapshots")).expanduser()
    before = len(snapshots_in(dest))
    prune(dest, args.keep)
    after = len(snapshots_in(dest))
    print(f"✅ 清理完成：{before} → {after} 份（保留最近 {args.keep} 份时间戳快照）")
    return 0


if __name__ == "__main__":
    a = parse_args()
    sys.exit(a.func(a, load_cfg()))
