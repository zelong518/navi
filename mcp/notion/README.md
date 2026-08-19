# notion MCP Server

通过 MCP（Model Context Protocol）连接 [Notion](https://www.notion.so/)，让 Claude 直接读写你的
Notion 笔记：搜索、读页面、查数据库，以及新建页面 / 追加内容 / 改块 / 归档。

## 能力

| 工具 | 说明 |
|------|------|
| `search` | 按标题搜页面/数据库（Notion 官方 search 只搜标题，不搜正文）|
| `list_databases` | 列出有权限的全部数据库（拿 `database_id`）|
| `get_database` | 看数据库字段 schema（写行前先对齐属性名/类型）|
| `get_page` | 读页面：属性 + 正文，递归子块转成 markdown |
| `query_database` | 查数据库的行，支持 `filter` / `sorts` |
| `create_page` | 新建页面（父级可为数据库或页面），正文写 markdown |
| `append_markdown` | 往页面末尾追加 markdown |
| `update_block` | 改写单个块的文本 |
| `update_page` | 改标题 / 属性 / 归档（`archived=true` 即删除到回收站）|
| `delete_block` | 删除单个块 |

markdown 支持：标题（h1–h3，更深降级）、有序/无序列表（按缩进嵌套）、任务列表、引用、
代码块（带语言）、表格、分割线、行内粗体/斜体/删除线/行内码/链接。

## 配置

`~/.navi/config.toml` 的 `[notion]` 段：

```toml
[notion]
token       = "ntn_xxx"      # Internal Integration Secret，必填
database_id = "32位ID"       # 可选，create_page 的默认父级
version     = "2022-06-28"   # 可选，Notion-Version
```

在 `.mcp.json` 注册（仓库根目录，该文件被 gitignore，需本机自建）：

```json
{
  "mcpServers": {
    "notion": { "command": "node", "args": ["mcp/notion/index.js"] }
  }
}
```

## 拿 token 的两步

1. https://www.notion.so/profile/integrations → **New integration** → Type 选 **Internal**，
   Capabilities 勾 **Read / Update / Insert content** → 复制 Internal Integration Secret。
2. **必做**：打开要给 Claude 访问的页面或数据库 → 右上角 `···` → **连接 / Connections** →
   添加该集成。新集成默认看不到任何内容，漏了这步所有请求都会 `object_not_found`。
   加在父页面上子页面自动继承，所以建议挂一个顶层页面，把要共享的内容都放它下面。

## 已知边界

- Notion 的 `search` 只匹配标题；要按正文找内容，先 `search` 缩小范围再 `get_page` 读。
- 单次请求最多 100 个子块、单段文本最多 2000 字符 —— 脚本已自动分批 / 切段。
- 表格最多写入 100 行；读取递归深度上限 4 层。
- API 限流约 3 请求/秒，触发会报 `rate_limited`。
- `2025-09-03` 及之后的 API 版本把 database 拆成了 data source（`parent` 改用
  `data_source_id`），本 server 固定用 `2022-06-28` 语义，不要随手改 `version`。

## 文件结构

- `index.js` — MCP Server 实现（认证 / 工具定义 / 分页与分批）
- `markdown.js` — Notion block ⇄ markdown 双向转换（纯函数，不碰网络）
- `package.json` — 依赖声明

## 安装依赖

```bash
cd mcp/notion && npm install
```
