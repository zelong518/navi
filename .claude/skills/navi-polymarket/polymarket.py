#!/usr/bin/env python3
"""polymarket.py — 查 Polymarket 资产 / 持仓 / 流水 / 行情，并管理本地策略库。

**只读**：本脚本不下单、不签名、不碰私钥。查询全部走公开端点，只需要你的
钱包地址（proxy wallet）。下单是不可逆的真金白银操作，不在本 skill 范围内。

三个已实测的公开 API（2026-08 验证）：
  data-api.polymarket.com   /value /positions /activity /holders   —— 账户维度，无鉴权
  gamma-api.polymarket.com  /markets                               —— 市场元数据
  clob.polymarket.com       /book /midpoint /price /spread /prices-history —— 行情

设计原则（沿用 navi 惯例）：脚本只回**裸数据 + 轻聚合**，不做判断；
"这个仓位该不该砍" 交给 skill 编排里的模型去分析。

用法：
    python3 polymarket.py assets                      # 资产总览（市值/成本/盈亏）
    python3 polymarket.py positions --min 1 --sort pnl # 持仓明细
    python3 polymarket.py activity --limit 20          # 近期成交流水
    python3 polymarket.py market <slug|conditionId>    # 某市场行情 + 订单簿 + 历史
    python3 polymarket.py strategy list                # 本地策略库
    python3 polymarket.py strategy add <名字> [--file f]  # 登记/更新一个策略
    python3 polymarket.py strategy show <名字>
    python3 polymarket.py analyze [策略名]              # 吐分析所需的裸数据（JSON）

任何子命令都可加 --json 输出原始 JSON；--address 覆盖配置里的地址。

配置：$NAVI_HOME/config.toml 的 [polymarket] 段：
    [polymarket]
    address = "0x..."          # 你的 proxy wallet（polymarket.com/profile/0x... 里那个）
    # strategies = "~/..."     # 可选，策略库目录，默认 $NAVI_HOME/polymarket/strategies
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # py<3.11
    import tomli as tomllib  # type: ignore

# 配置目录：环境变量 NAVI_HOME 优先，未设置则默认 ~/.navi
NAVI_HOME = Path(os.environ.get("NAVI_HOME") or "~/.navi").expanduser()
CONFIG_PATH = NAVI_HOME / "config.toml"

DATA = "https://data-api.polymarket.com"
GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
UA = "navi-polymarket/1.0"


def load_cfg() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH, "rb") as f:
        return tomllib.load(f).get("polymarket") or {}


def get(base: str, path: str, params: dict | None = None, timeout: int = 30):
    url = f"{base}{path}"
    if params:
        clean = {k: v for k, v in params.items() if v not in (None, "")}
        url += "?" + urllib.parse.urlencode(clean)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:200]
        raise SystemExit(f"❌ {base}{path} HTTP {e.code}: {body}")
    except urllib.error.URLError as e:
        raise SystemExit(f"❌ 网络错误访问 {base}: {e.reason}")
    except json.JSONDecodeError:
        raise SystemExit(f"❌ {base}{path} 返回的不是 JSON")


def need_address(args, cfg) -> str:
    addr = args.address or cfg.get("address")
    if not addr:
        raise SystemExit(
            f"缺少钱包地址：用 --address 传入，或在 {CONFIG_PATH} 的 [polymarket] 段填 address。\n"
            "地址是你的 proxy wallet —— 打开 polymarket.com 个人主页，URL 里 /profile/0x... 那一串。")
    return addr.strip()


def jdump(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def usd(x) -> str:
    try:
        x = float(x)
    except (TypeError, ValueError):
        return "-"
    return f"{x:,.2f}"


def pct(x) -> str:
    try:
        return f"{float(x):+.1f}%"
    except (TypeError, ValueError):
        return "-"


def fetch_positions(addr: str, min_size: float = 1.0, limit: int = 500) -> list:
    return get(DATA, "/positions", {"user": addr, "sizeThreshold": min_size, "limit": limit}) or []


# ---------------- 子命令 ----------------

def cmd_assets(args, cfg) -> int:
    addr = need_address(args, cfg)
    val = get(DATA, "/value", {"user": addr})
    portfolio = float(val[0]["value"]) if val else 0.0
    pos = fetch_positions(addr, args.min)

    cost = sum(float(p.get("initialValue") or 0) for p in pos)
    mkt = sum(float(p.get("currentValue") or 0) for p in pos)
    unreal = sum(float(p.get("cashPnl") or 0) for p in pos)
    real = sum(float(p.get("realizedPnl") or 0) for p in pos)
    redeemable = [p for p in pos if p.get("redeemable")]

    out = {
        "address": addr,
        "portfolio_value": portfolio,
        "positions_count": len(pos),
        "positions_cost": cost,
        "positions_market_value": mkt,
        "unrealized_pnl": unreal,
        "unrealized_pnl_pct": (unreal / cost * 100) if cost else None,
        "realized_pnl": real,
        "redeemable_count": len(redeemable),
        "redeemable_value": sum(float(p.get("currentValue") or 0) for p in redeemable),
        "top_positions": sorted(pos, key=lambda p: -float(p.get("currentValue") or 0))[:5],
    }
    if args.json:
        jdump(out)
        return 0

    print(f"Polymarket 资产总览  {addr}")
    print(f"  组合估值    ${usd(portfolio)}")
    print(f"  持仓        {len(pos)} 个（阈值 size>={args.min}）")
    print(f"  持仓成本    ${usd(cost)}")
    print(f"  持仓市值    ${usd(mkt)}")
    print(f"  未实现盈亏  ${usd(unreal)}  ({pct(out['unrealized_pnl_pct'])})")
    print(f"  已实现盈亏  ${usd(real)}")
    if out["redeemable_value"] > 0.01:
        print(f"  ⚠️ 可赎回    {len(redeemable)} 个仓位，${usd(out['redeemable_value'])} —— 已结算待领回")
    elif redeemable:
        print(f"  已结算      {len(redeemable)} 个仓位，可赎回价值 ${usd(out['redeemable_value'])}（归零，无需操作）")
    if out["top_positions"]:
        print("  最大仓位：")
        for p in out["top_positions"]:
            print(f"    ${usd(p.get('currentValue'))}  {pct(p.get('percentPnl'))}  "
                  f"{p.get('outcome')} @ {p.get('curPrice')}  {(p.get('title') or '')[:52]}")
    return 0


def cmd_positions(args, cfg) -> int:
    addr = need_address(args, cfg)
    pos = fetch_positions(addr, args.min)
    keys = {"pnl": lambda p: float(p.get("cashPnl") or 0),
            "value": lambda p: -float(p.get("currentValue") or 0),
            "pct": lambda p: float(p.get("percentPnl") or 0),
            "end": lambda p: str(p.get("endDate") or "")}
    pos.sort(key=keys[args.sort])
    if args.json:
        jdump(pos)
        return 0
    if not pos:
        print(f"{addr} 没有 size>={args.min} 的持仓。")
        return 0
    print(f"{len(pos)} 个持仓（按 {args.sort} 排序）\n")
    for p in pos:
        flag = " 🔓可赎回" if p.get("redeemable") else ""
        print(f"[{p.get('outcome')}] {(p.get('title') or '')[:64]}{flag}")
        print(f"   size {float(p.get('size') or 0):,.0f}  均价 {p.get('avgPrice')} → 现价 {p.get('curPrice')}"
              f"   市值 ${usd(p.get('currentValue'))}  盈亏 ${usd(p.get('cashPnl'))} ({pct(p.get('percentPnl'))})")
        print(f"   到期 {str(p.get('endDate'))[:10]}   slug {p.get('slug')}")
    return 0


def cmd_activity(args, cfg) -> int:
    addr = need_address(args, cfg)
    acts = get(DATA, "/activity", {"user": addr, "limit": args.limit}) or []
    if args.json:
        jdump(acts)
        return 0
    if not acts:
        print("没有流水。")
        return 0
    print(f"最近 {len(acts)} 条流水\n")
    for a in acts:
        ts = datetime.fromtimestamp(a.get("timestamp", 0), timezone.utc).strftime("%m-%d %H:%M")
        print(f"{ts}  {a.get('type','?'):<8} {a.get('side') or '':<4} "
              f"{float(a.get('size') or 0):>10,.0f} @ {a.get('price')}  "
              f"${usd(a.get('usdcSize'))}  {(a.get('title') or '')[:44]}")
    return 0


def resolve_market(ref: str) -> dict | None:
    """slug / conditionId(0x..) / gamma id 都能查到市场元数据。"""
    ref = ref.strip()
    if ref.startswith("0x"):
        r = get(GAMMA, "/markets", {"condition_ids": ref})
    elif ref.isdigit() and len(ref) < 12:
        r = get(GAMMA, "/markets", {"id": ref})
    else:
        r = get(GAMMA, "/markets", {"slug": ref})
    if isinstance(r, dict):
        r = r.get("data") or [r]
    return r[0] if r else None


def cmd_market(args, cfg) -> int:
    m = resolve_market(args.ref)
    if not m:
        raise SystemExit(f"找不到市场 {args.ref!r}（可给 slug、conditionId 或 gamma id）")

    def parse_list(v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return [v]
        return v or []

    tokens = parse_list(m.get("clobTokenIds"))
    outcomes = parse_list(m.get("outcomes"))
    legs = []
    for i, tok in enumerate(tokens):
        book = get(CLOB, "/book", {"token_id": tok})
        bids, asks = book.get("bids") or [], book.get("asks") or []
        leg = {
            "outcome": outcomes[i] if i < len(outcomes) else f"#{i}",
            "token_id": tok,
            "midpoint": (get(CLOB, "/midpoint", {"token_id": tok}) or {}).get("mid"),
            "spread": (get(CLOB, "/spread", {"token_id": tok}) or {}).get("spread"),
            "best_bid": bids[-1] if bids else None,
            "best_ask": asks[-1] if asks else None,
            "bid_depth_usd": sum(float(b["price"]) * float(b["size"]) for b in bids),
            "ask_depth_usd": sum(float(a["price"]) * float(a["size"]) for a in asks),
        }
        if args.history:
            h = get(CLOB, "/prices-history",
                    {"market": tok, "interval": args.history, "fidelity": 60}).get("history") or []
            leg["history_points"] = len(h)
            if h:
                leg["history_first"], leg["history_last"] = h[0], h[-1]
                leg["history_min"] = min(x["p"] for x in h)
                leg["history_max"] = max(x["p"] for x in h)
        legs.append(leg)

    out = {"question": m.get("question"), "slug": m.get("slug"),
           "conditionId": m.get("conditionId"), "endDate": m.get("endDate"),
           "closed": m.get("closed"), "liquidity": m.get("liquidity"),
           "volume24hr": m.get("volume24hr"), "volume": m.get("volume"),
           "description": (m.get("description") or "")[:600], "legs": legs}
    if args.json:
        jdump(out)
        return 0
    print(f"{out['question']}")
    print(f"  slug {out['slug']}   到期 {str(out['endDate'])[:10]}   closed={out['closed']}")
    print(f"  流动性 ${usd(out['liquidity'])}   24h量 ${usd(out['volume24hr'])}   总量 ${usd(out['volume'])}")
    for leg in legs:
        print(f"\n  [{leg['outcome']}] mid {leg['midpoint']}  spread {leg['spread']}")
        print(f"     best bid {leg['best_bid']}   best ask {leg['best_ask']}")
        print(f"     簿内深度  买 ${usd(leg['bid_depth_usd'])} / 卖 ${usd(leg['ask_depth_usd'])}")
        if "history_min" in leg:
            print(f"     {args.history} 区间 {leg['history_min']} – {leg['history_max']}"
                  f"（{leg['history_points']} 点）")
    return 0


# ---------------- 本地策略库 ----------------

TEMPLATE = """---
name: {name}
created: {now}
status: draft            # draft | live | paused | retired
---

## 论点
一句话说清：为什么这个市场的定价是错的，错在哪。

## 标的
- 市场（slug 或 conditionId）：
- 方向（哪个 outcome）：

## 入场
- 触发条件（价格 / 时间 / 外部事件）：
- 目标价位与最多吃多少深度：

## 出场
- 止盈：
- 止损：
- 时间止损（到期前多久无条件平）：

## 仓位与风控
- 单笔上限（占组合 %）：
- 与现有持仓的相关性（别把同一个宏观赌注下三遍）：

## 复盘
- 事后记录：实际成交价、滑点、结论对错、下次改什么
"""


def strategies_dir(cfg) -> Path:
    d = cfg.get("strategies") or (NAVI_HOME / "polymarket" / "strategies")
    p = Path(os.path.expanduser(str(d)))
    p.mkdir(parents=True, exist_ok=True)
    return p


def cmd_strategy(args, cfg) -> int:
    d = strategies_dir(cfg)
    if args.op == "list":
        files = sorted(d.glob("*.md"))
        if args.json:
            jdump([{"name": f.stem, "path": str(f),
                    "bytes": f.stat().st_size,
                    "mtime": datetime.fromtimestamp(f.stat().st_mtime).isoformat(" ", "seconds")}
                   for f in files])
            return 0
        if not files:
            print(f"{d} 下还没有策略。用 `strategy add <名字>` 建一个。")
            return 0
        print(f"{d}（{len(files)} 个）\n")
        for f in files:
            head = f.read_text(encoding="utf-8").splitlines()
            status = next((l.split(":", 1)[1].strip().split()[0]
                           for l in head[:8] if l.startswith("status:")), "?")
            print(f"- {f.stem:<24} status={status:<8} "
                  f"{datetime.fromtimestamp(f.stat().st_mtime).strftime('%m-%d %H:%M')}")
        return 0

    if not args.name:
        raise SystemExit(f"{args.op} 需要策略名字。")
    f = d / f"{args.name}.md"

    if args.op == "show":
        if not f.exists():
            raise SystemExit(f"策略 {args.name!r} 不存在（{d}）")
        print(f.read_text(encoding="utf-8"))
        return 0

    # add —— 从文件 / stdin / 模板落盘；已存在则覆盖前留 .bak
    if args.file == "-":
        body = sys.stdin.read()
    elif args.file:
        body = Path(args.file).expanduser().read_text(encoding="utf-8")
    else:
        body = TEMPLATE.format(name=args.name,
                               now=datetime.now().astimezone().isoformat(" ", "seconds"))
    existed = f.exists()
    if existed:
        f.with_suffix(".md.bak").write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
    f.write_text(body, encoding="utf-8")
    print(f"{'♻️  已更新' if existed else '✅ 已登记'}策略：{f}"
          + ("（原文件备份为 .md.bak）" if existed else ""))
    if not args.file:
        print("   写入的是空模板，按里面的小节填完再用。")
    return 0


def cmd_analyze(args, cfg) -> int:
    """吐出分析所需的全部裸数据，判断交给模型。"""
    addr = need_address(args, cfg)
    pos = fetch_positions(addr, args.min)
    val = get(DATA, "/value", {"user": addr})
    out = {
        "generated_at": datetime.now().astimezone().isoformat(" ", "seconds"),
        "address": addr,
        "portfolio_value": float(val[0]["value"]) if val else 0.0,
        "positions": [],
        "recent_activity": get(DATA, "/activity", {"user": addr, "limit": args.activity}) or [],
    }
    for p in pos[: args.top]:
        tok = p.get("asset")
        live = {}
        if tok:
            live["midpoint"] = (get(CLOB, "/midpoint", {"token_id": tok}) or {}).get("mid")
            live["spread"] = (get(CLOB, "/spread", {"token_id": tok}) or {}).get("spread")
            h = (get(CLOB, "/prices-history",
                     {"market": tok, "interval": "1w", "fidelity": 360}) or {}).get("history") or []
            if h:
                live["week_first"], live["week_last"] = h[0]["p"], h[-1]["p"]
                live["week_min"], live["week_max"] = min(x["p"] for x in h), max(x["p"] for x in h)
        out["positions"].append({k: p.get(k) for k in (
            "title", "slug", "outcome", "size", "avgPrice", "curPrice", "initialValue",
            "currentValue", "cashPnl", "percentPnl", "realizedPnl", "redeemable",
            "endDate", "conditionId", "asset")} | {"live": live})

    if args.strategy:
        f = strategies_dir(cfg) / f"{args.strategy}.md"
        if not f.exists():
            raise SystemExit(f"策略 {args.strategy!r} 不存在（{strategies_dir(cfg)}）")
        out["strategy"] = {"name": args.strategy, "text": f.read_text(encoding="utf-8")}
    jdump(out)
    return 0


def parse_args():
    ap = argparse.ArgumentParser(description="Polymarket 资产 / 持仓 / 行情 / 策略（只读，不下单）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    # 公共参数：放 parent 里，这样能写在子命令**后面**（更符合直觉）
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--address", help="钱包地址（proxy wallet），覆盖配置")
    common.add_argument("--json", action="store_true", help="输出原始 JSON")

    a = sub.add_parser("assets", aliases=["portfolio"], parents=[common],
                       help="资产总览：估值 / 成本 / 盈亏 / 可赎回")
    a.add_argument("--min", type=float, default=1.0, help="持仓 size 阈值，默认 1")
    a.set_defaults(func=cmd_assets)

    p = sub.add_parser("positions", aliases=["pos"], parents=[common], help="持仓明细")
    p.add_argument("--min", type=float, default=1.0, help="size 阈值，默认 1")
    p.add_argument("--sort", choices=["pnl", "value", "pct", "end"], default="value",
                   help="排序键，默认 value（市值降序）")
    p.set_defaults(func=cmd_positions)

    c = sub.add_parser("activity", aliases=["trades"], parents=[common], help="近期成交流水")
    c.add_argument("--limit", type=int, default=20, help="条数，默认 20")
    c.set_defaults(func=cmd_activity)

    m = sub.add_parser("market", parents=[common], help="某市场的行情 / 订单簿 / 价格历史")
    m.add_argument("ref", help="slug、conditionId(0x..) 或 gamma id")
    m.add_argument("--history", default="1w", help="价格历史区间：1d/1w/1m/max，默认 1w；给空串跳过")
    m.set_defaults(func=cmd_market)

    s = sub.add_parser("strategy", aliases=["strat"], parents=[common], help="本地策略库：list / add / show")
    s.add_argument("op", choices=["list", "add", "show"])
    s.add_argument("name", nargs="?", help="策略名字（add / show 必填）")
    s.add_argument("--file", help="add 的正文来源：文件路径或 '-' 读 stdin；省略则写空模板")
    s.set_defaults(func=cmd_strategy)

    z = sub.add_parser("analyze", parents=[common], help="吐出分析所需裸数据（持仓 + 实时行情 + 可选策略）")
    z.add_argument("strategy", nargs="?", help="可选：一并带上这个策略的正文")
    z.add_argument("--min", type=float, default=1.0, help="size 阈值，默认 1")
    z.add_argument("--top", type=int, default=15, help="最多分析多少个仓位，默认 15")
    z.add_argument("--activity", type=int, default=30, help="带多少条流水，默认 30")
    z.set_defaults(func=cmd_analyze)
    return ap.parse_args()


if __name__ == "__main__":
    args = parse_args()
    sys.exit(args.func(args, load_cfg()))
