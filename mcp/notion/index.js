/**
 * Notion MCP Server — 让 Claude 读写你的 Notion 笔记。
 *
 * 认证读 ~/.navi/config.toml 的 [notion] 段：
 *   [notion]
 *   token       = "ntn_..."   # Internal Integration Secret（必填）
 *   database_id = "32位ID"    # 可选，create_page 默认父级
 *   version     = "2022-06-28" # 可选，Notion-Version
 *
 * 注意：新建的集成默认看不到任何页面，需要在目标页面 ··· → 连接 → 添加该集成。
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";
import { parse as parseToml } from "smol-toml";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import {
  mdToBlocks,
  mdToSingleRichText,
  renderBlock,
  richTextToMd,
  MAX_CHILDREN,
} from "./markdown.js";

// 配置目录：环境变量 NAVI_HOME 优先，未设置则默认 ~/.navi
const naviHome = process.env.NAVI_HOME || join(homedir(), ".navi");
const configPath = join(naviHome, "config.toml");
let cfg = {};
try {
  cfg = parseToml(readFileSync(configPath, "utf-8")).notion || {};
} catch {
  cfg = {}; // 配置缺失不阻塞握手，等真正调用时再报错
}

const TOKEN = cfg.token || process.env.NOTION_TOKEN || "";
const VERSION = cfg.version || "2022-06-28";
const DEFAULT_PARENT = cfg.database_id || cfg.page_id || "";
const MAX_OUTPUT = 60000; // 单次返回的 markdown 上限，防止撑爆上下文

/* ---------------- HTTP ---------------- */

const HINTS = {
  unauthorized: "token 无效或已撤销，检查 ~/.navi/config.toml 的 [notion].token",
  restricted_resource: "集成权限不足（新建时要勾 Read/Update/Insert content）",
  object_not_found:
    "对象不存在，或**集成没被添加到该页面**：打开该页面 → 右上角 ··· → 连接 → 添加你的集成",
  validation_error: "参数不合法（常见：ID 格式错、属性名与数据库 schema 对不上）",
  rate_limited: "触发频率限制（约 3 次/秒），稍后重试",
};

/** ID 归一：Notion 接受带/不带连字符的 32 位十六进制，URL 里粘来的也直接处理。 */
function normId(id) {
  const s = String(id || "").trim();
  const hex = s.replace(/^https?:\/\/[^\s]*?([0-9a-fA-F]{32})(?:[?#].*)?$/, "$1").replace(/-/g, "");
  const m = hex.match(/([0-9a-fA-F]{32})/);
  return m ? m[1] : s;
}

async function api(path, { method = "GET", body, query } = {}) {
  if (!TOKEN) {
    throw new Error(
      `缺少 Notion token：在 ${configPath} 的 [notion] 段填 token = "ntn_..."（Internal Integration Secret）`
    );
  }
  const url = new URL(`https://api.notion.com/v1${path}`);
  for (const [k, v] of Object.entries(query || {})) {
    if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, v);
  }
  const res = await fetch(url, {
    method,
    headers: {
      Authorization: `Bearer ${TOKEN}`,
      "Notion-Version": VERSION,
      "Content-Type": "application/json",
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const json = await res.json().catch(() => ({}));
  if (!res.ok) {
    const hint = HINTS[json.code];
    throw new Error(
      `Notion API ${res.status} ${json.code || ""}: ${json.message || "未知错误"}` +
        (hint ? `\n→ ${hint}` : "")
    );
  }
  return json;
}

const text = (s) => ({ content: [{ type: "text", text: String(s).slice(0, MAX_OUTPUT) }] });

/* ---------------- 属性 / 标题 ---------------- */

function pageTitle(obj) {
  if (obj.object === "database") return richTextToMd(obj.title || []) || "(无标题)";
  for (const v of Object.values(obj.properties || {})) {
    if (v.type === "title") return richTextToMd(v.title) || "(无标题)";
  }
  return "(无标题)";
}

function propValue(v) {
  if (!v) return "";
  switch (v.type) {
    case "title":
    case "rich_text":
      return richTextToMd(v[v.type]);
    case "select":
      return v.select?.name ?? "";
    case "status":
      return v.status?.name ?? "";
    case "multi_select":
      return (v.multi_select || []).map((o) => o.name).join(", ");
    case "date":
      return v.date ? [v.date.start, v.date.end].filter(Boolean).join(" → ") : "";
    case "checkbox":
      return v.checkbox ? "✅" : "☐";
    case "number":
      return v.number ?? "";
    case "url":
    case "email":
    case "phone_number":
      return v[v.type] ?? "";
    case "people":
      return (v.people || []).map((p) => p.name || p.id).join(", ");
    case "files":
      return (v.files || []).map((f) => f.name).join(", ");
    case "relation":
      return (v.relation || []).map((r) => r.id).join(", ");
    case "formula":
      return String(v.formula?.[v.formula?.type] ?? "");
    case "rollup":
      return String(v.rollup?.number ?? v.rollup?.array?.length ?? "");
    case "created_time":
    case "last_edited_time":
      return v[v.type];
    default:
      return "";
  }
}

function propsLine(page) {
  return Object.entries(page.properties || {})
    .filter(([, v]) => v.type !== "title")
    .map(([k, v]) => [k, propValue(v)])
    .filter(([, val]) => val !== "" && val !== null && val !== undefined)
    .map(([k, val]) => `${k}: ${val}`)
    .join(" · ");
}

/* ---------------- 块读写 ---------------- */

async function listChildren(blockId) {
  const out = [];
  let cursor;
  do {
    const data = await api(`/blocks/${normId(blockId)}/children`, {
      query: { page_size: 100, start_cursor: cursor },
    });
    out.push(...(data.results || []));
    cursor = data.has_more ? data.next_cursor : null;
  } while (cursor);
  return out;
}

/** 递归把一个页面/块的子树渲染成 markdown。 */
async function subtreeToMd(blockId, depth = 0, withIds = false) {
  if (depth > 4) return "";
  const blocks = await listChildren(blockId);
  const lines = [];
  for (const b of blocks) {
    const recurse = b.has_children && b.type !== "child_page" && b.type !== "child_database";
    const childMd = recurse ? await subtreeToMd(b.id, depth + 1, withIds) : "";
    let line = renderBlock(b, childMd);
    if (withIds && line) line += `  <!--${b.id}-->`;
    if (line !== "") lines.push(line);
  }
  return lines.join("\n");
}

/** children 超过 100 个要分批 append。 */
async function appendBlocks(parentId, blocks) {
  for (let i = 0; i < blocks.length; i += MAX_CHILDREN) {
    await api(`/blocks/${normId(parentId)}/children`, {
      method: "PATCH",
      body: { children: blocks.slice(i, i + MAX_CHILDREN) },
    });
  }
  return blocks.length;
}

/* ---------------- MCP Server ---------------- */

const server = new McpServer({ name: "notion", version: "1.0.0" });

// --- 读 ---

server.tool(
  "search",
  "按标题搜索有权限的页面和数据库（Notion 只搜标题，不搜正文）",
  {
    query: z.string().default("").describe("关键词，留空则列出全部有权限的对象"),
    type: z.enum(["page", "database", "all"]).default("all").describe("只搜页面 / 只搜数据库 / 都要"),
    page_size: z.number().int().min(1).max(100).default(20),
  },
  async ({ query, type, page_size }) => {
    const body = { query, page_size };
    if (type !== "all") body.filter = { property: "object", value: type };
    const data = await api("/search", { method: "POST", body });
    const results = data.results || [];
    if (!results.length) return text("无结果（若确信存在，多半是集成没被添加到该页面的「连接」里）");
    const lines = results.map(
      (r) => `- [${r.object === "database" ? "🗂" : "📄"}] ${pageTitle(r)}\n  id: ${r.id}\n  url: ${r.url || ""}`
    );
    if (data.has_more) lines.push("\n（还有更多结果，可缩小 query 或调大 page_size）");
    return text(lines.join("\n"));
  }
);

server.tool("list_databases", "列出集成有权限访问的全部数据库（拿 database_id 用）", {}, async () => {
  const data = await api("/search", {
    method: "POST",
    body: { filter: { property: "object", value: "database" }, page_size: 100 },
  });
  const list = (data.results || []).map((d) => `- ${pageTitle(d)}  id: ${d.id}`);
  return text(list.join("\n") || "没有可访问的数据库（去目标数据库 ··· → 连接 → 添加集成）");
});

server.tool(
  "get_database",
  "查看数据库的字段 schema（写入行之前先看这个，属性名/类型要对得上）",
  { database_id: z.string().describe("数据库 ID") },
  async ({ database_id }) => {
    const db = await api(`/databases/${normId(database_id)}`);
    const props = Object.entries(db.properties || {}).map(([k, v]) => {
      const opts = (v.select?.options || v.multi_select?.options || v.status?.options || [])
        .map((o) => o.name)
        .join(" | ");
      return `- ${k} (${v.type})${opts ? `: ${opts}` : ""}`;
    });
    return text(`# ${pageTitle(db)}\nid: ${db.id}\nurl: ${db.url || ""}\n\n## 字段\n${props.join("\n")}`);
  }
);

server.tool(
  "get_page",
  "读取一个页面：属性 + 正文（转成 markdown，递归子块）",
  {
    page_id: z.string().describe("页面 ID，或直接粘页面 URL"),
    with_block_ids: z.boolean().default(false).describe("每行尾部附块 ID，便于随后 update_block/delete_block"),
  },
  async ({ page_id, with_block_ids }) => {
    const id = normId(page_id);
    const page = await api(`/pages/${id}`);
    const props = propsLine(page);
    const md = await subtreeToMd(id, 0, with_block_ids);
    return text(
      `# ${pageTitle(page)}\nid: ${page.id}\nurl: ${page.url || ""}` +
        (props ? `\n属性: ${props}` : "") +
        `\n\n---\n\n${md || "(空页面)"}`
    );
  }
);

server.tool(
  "query_database",
  "查询数据库的行（可带 filter / sorts，语法见 Notion API 文档）",
  {
    database_id: z.string().describe("数据库 ID"),
    filter: z.string().default("").describe('可选，filter 的 JSON 字符串，如 {"property":"Status","status":{"equals":"Done"}}'),
    sorts: z.string().default("").describe('可选，sorts 的 JSON 字符串，如 [{"timestamp":"created_time","direction":"descending"}]'),
    page_size: z.number().int().min(1).max(100).default(25),
  },
  async ({ database_id, filter, sorts, page_size }) => {
    const body = { page_size };
    if (filter.trim()) body.filter = JSON.parse(filter);
    if (sorts.trim()) body.sorts = JSON.parse(sorts);
    const data = await api(`/databases/${normId(database_id)}/query`, { method: "POST", body });
    const rows = (data.results || []).map((p) => {
      const props = propsLine(p);
      return `- ${pageTitle(p)}\n  id: ${p.id}${props ? `\n  ${props}` : ""}`;
    });
    const tail = data.has_more ? "\n\n（还有更多行）" : "";
    return text((rows.join("\n") || "无匹配行") + tail);
  }
);

// --- 写 ---

server.tool(
  "create_page",
  "新建页面（父级可以是数据库或页面），正文用 markdown 写",
  {
    title: z.string().describe("页面标题"),
    markdown: z.string().default("").describe("正文（markdown：标题/列表/代码块/表格/待办都支持）"),
    parent_id: z.string().default("").describe("父数据库或父页面 ID；留空用配置里的 [notion].database_id"),
    parent_type: z.enum(["database", "page"]).default("database").describe("父级类型"),
    properties: z.string().default("").describe('可选，额外属性的 JSON 字符串（父级是数据库时用），如 {"Tags":{"multi_select":[{"name":"AI"}]}}'),
  },
  async ({ title, markdown, parent_id, parent_type, properties }) => {
    const pid = normId(parent_id || DEFAULT_PARENT);
    if (!pid) throw new Error("没给 parent_id，配置里也没有 [notion].database_id");

    const blocks = mdToBlocks(markdown);
    const body = {
      parent: parent_type === "page" ? { page_id: pid } : { database_id: pid },
      properties:
        parent_type === "page"
          ? { title: { title: [{ type: "text", text: { content: title } }] } }
          : { ...(properties.trim() ? JSON.parse(properties) : {}) },
      children: blocks.slice(0, MAX_CHILDREN),
    };
    if (parent_type === "database") {
      // 数据库的标题属性名各不相同，取 schema 里 type=title 的那个
      const db = await api(`/databases/${pid}`);
      const titleKey =
        Object.entries(db.properties || {}).find(([, v]) => v.type === "title")?.[0] || "Name";
      body.properties[titleKey] = { title: [{ type: "text", text: { content: title } }] };
    }

    const page = await api("/pages", { method: "POST", body });
    const rest = blocks.slice(MAX_CHILDREN);
    if (rest.length) await appendBlocks(page.id, rest);
    return text(`✅ 已创建：${title}\nid: ${page.id}\nurl: ${page.url || ""}\n块数: ${blocks.length}`);
  }
);

server.tool(
  "append_markdown",
  "把 markdown 追加到页面（或某个块）末尾",
  {
    page_id: z.string().describe("页面 ID（也可以是任意支持子块的块 ID）"),
    markdown: z.string().describe("要追加的 markdown"),
  },
  async ({ page_id, markdown }) => {
    const blocks = mdToBlocks(markdown);
    if (!blocks.length) throw new Error("markdown 解析后为空，没有可追加的内容");
    const n = await appendBlocks(page_id, blocks);
    return text(`✅ 已追加 ${n} 个块到 ${normId(page_id)}`);
  }
);

server.tool(
  "update_block",
  "改写某个块的文本内容（块类型不变；用 get_page 的 with_block_ids 拿 ID）",
  {
    block_id: z.string().describe("块 ID"),
    markdown: z.string().describe("新内容（单块，取首行格式）"),
  },
  async ({ block_id, markdown }) => {
    const id = normId(block_id);
    const cur = await api(`/blocks/${id}`);
    if (!cur[cur.type]?.rich_text) throw new Error(`块类型 ${cur.type} 没有可改写的文本`);
    await api(`/blocks/${id}`, {
      method: "PATCH",
      body: { [cur.type]: { rich_text: mdToSingleRichText(markdown) } },
    });
    return text(`✅ 已更新块 ${id}（${cur.type}）`);
  }
);

server.tool(
  "update_page",
  "改页面标题 / 属性 / 归档（删除页面用 archived=true）",
  {
    page_id: z.string().describe("页面 ID"),
    title: z.string().default("").describe("新标题，留空不改"),
    properties: z.string().default("").describe("可选，属性的 JSON 字符串"),
    archived: z.boolean().optional().describe("true = 移入回收站，false = 恢复"),
  },
  async ({ page_id, title, properties, archived }) => {
    const id = normId(page_id);
    const body = {};
    if (properties.trim()) body.properties = JSON.parse(properties);
    if (title) {
      const page = await api(`/pages/${id}`);
      const titleKey =
        Object.entries(page.properties || {}).find(([, v]) => v.type === "title")?.[0] || "title";
      body.properties = {
        ...(body.properties || {}),
        [titleKey]: { title: [{ type: "text", text: { content: title } }] },
      };
    }
    if (archived !== undefined) body.archived = archived;
    if (!Object.keys(body).length) throw new Error("没有要改的内容");
    const page = await api(`/pages/${id}`, { method: "PATCH", body });
    return text(`✅ 已更新页面 ${page.id}${archived ? "（已归档）" : ""}`);
  }
);

server.tool(
  "delete_block",
  "删除一个块（移入回收站，可在 Notion 里恢复）",
  { block_id: z.string().describe("块 ID") },
  async ({ block_id }) => {
    const id = normId(block_id);
    await api(`/blocks/${id}`, { method: "DELETE" });
    return text(`✅ 已删除块 ${id}`);
  }
);

// --- Start ---

const transport = new StdioServerTransport();
await server.connect(transport);
