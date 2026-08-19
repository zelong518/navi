---
name: navi-polymarket
description: 查 Polymarket 预测市场的资产、持仓、成交流水与单个市场行情（订单簿深度 / 价差 / 价格历史），管理本地策略库（登记 / 查看 / 更新策略），并对持仓做分析。**只读**——不下单、不签名、不碰私钥。触发词："polymarket"、"预测市场"、"我的持仓"、"仓位"、"盈亏"、"资产"、"策略"、"下注分析"、"赔率"、"订单簿"。
argument-hint: "assets | positions [--sort pnl|value|pct|end=value] | activity [--limit=20] | market <slug> | strategy list|add|show <名字> | analyze [策略名]"
user-invocable: true
allowed-tools: Bash, Read, Write
---

# Polymarket 资产 / 持仓 / 策略

**⛔ 只读边界**：本 skill 只查询，**绝不下单、不签名、不接触私钥**。
Polymarket 的下单是不可逆的真金白银操作，需要钱包私钥签 EIP-712；
本 skill 的所有端点都是公开只读的，只需要一个**公开钱包地址**。
用户要求下单时，明确说明本 skill 不做这件事，不要自行去调 CLOB 的下单接口。

## 用法

```bash
S="<base directory>/polymarket.py"        # 调用时给出的绝对路径

python3 $S assets                        # 资产总览：估值 / 成本 / 未实现+已实现盈亏 / 可赎回
python3 $S positions --sort pnl          # 持仓明细（value 市值降序=默认 / pnl / pct / end 到期）
python3 $S positions --min 100           # 只看 size>=100 的仓位（默认 1，滤掉灰尘仓）
python3 $S activity --limit 30           # 近期成交流水
python3 $S market <slug|conditionId>     # 单市场：mid / spread / 最优买卖 / 簿内深度 / 价格区间
python3 $S market <slug> --history 1m    # 价格历史区间 1d/1w/1m/max（默认 1w）

python3 $S strategy list                 # 本地策略库
python3 $S strategy add <名字>            # 写一份空模板（论点/标的/入场/出场/仓位风控/复盘）
python3 $S strategy add <名字> --file f.md # 从文件登记；'-' 读 stdin；同名会覆盖并留 .md.bak
python3 $S strategy show <名字>

python3 $S analyze                       # 吐分析所需裸数据（持仓 + 每仓实时行情 + 流水）
python3 $S analyze <策略名>               # 一并带上该策略正文，用于「持仓是否还符合策略」
```

任何子命令都可加 `--json`（原始 JSON）和 `--address 0x...`（覆盖配置里的地址）。

## 数据来源（均为公开端点，2026-08 实测）

| 端点 | 用途 |
|------|------|
| `data-api.polymarket.com/value` `/positions` `/activity` | 账户估值、持仓明细、成交流水 |
| `gamma-api.polymarket.com/markets` | 市场元数据（问题、slug、到期、流动性、成交量、两边 token） |
| `clob.polymarket.com/book` `/midpoint` `/spread` `/prices-history` | 订单簿、中间价、价差、价格历史 |

设计原则：**脚本只回裸数据 + 轻聚合**（求和、排序、算百分比），不做判断。
「这仓位该不该砍」由本 skill 的编排交给模型分析。

## 编排要求

1. **`analyze` 是给模型吃的**：它输出 JSON，你要基于它给出结论，至少覆盖——
   - 每个仓位：成本 vs 现价的偏离、一周区间里现价的位置、离到期多久
   - **流动性现实**：`spread` 与簿内深度决定「想跑跑不跑得掉」。深度 < 仓位市值时
     必须点出「按现价估的市值是虚的」——这是预测市场最容易骗人的地方
   - 组合层面：是否把同一个宏观赌注下了多遍（相关性）、单一仓位占比
2. **带策略时**（`analyze <策略名>`）逐条比对持仓与策略的入场/出场/风控条件，
   明确指出**哪一条已经被违反**，而不是泛泛地说「注意风险」。
3. **可赎回仓位**：`redeemable` 且 `currentValue > 0` 才提醒去 redeem；
   价值归零的已结算仓位不要提醒（那是已经输掉的，赎无可赎）。
4. **不要把 `curPrice` 当概率讲死**。它是市场报价，含流动性溢价与手续费摩擦；
   低价尾部仓位（<0.05）的百分比盈亏在数字上极夸张，解读时说清绝对金额。
5. 用户问「某个市场怎么样」时用 `market <slug>`，slug 从 Polymarket 网页 URL
   最后一段取。给了 conditionId（`0x` 开头 66 位）也能查。
6. 策略是**本地文件**（`$NAVI_HOME/polymarket/strategies/*.md`），
   `strategy add` 只写本地磁盘，**不会上传到 Polymarket 或任何外部服务**。
   想跨机同步就走 `/navi sync`（WebDAV）。
7. 涉及金额的输出一律带货币单位与绝对值，不要只给百分比。

## 配置

`$NAVI_HOME/config.toml` 的 `[polymarket]` 段：

```toml
[polymarket]
address = "0x..."        # 你的 proxy wallet 地址（必填）
# strategies = "~/..."   # 可选，策略库目录，默认 $NAVI_HOME/polymarket/strategies
```

**地址是 proxy wallet，不是你的 EOA**：打开 polymarket.com 自己的个人主页，
URL 里 `/profile/0x...` 那一串就是。它是公开信息，只能读、不能动钱。

## 文件结构

- `.claude/skills/navi-polymarket/SKILL.md` — 编排说明
- `.claude/skills/navi-polymarket/polymarket.py` — CLI（assets / positions / activity / market / strategy / analyze）
