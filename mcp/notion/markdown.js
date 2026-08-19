/**
 * markdown.js — Notion block ⇄ markdown 双向转换。
 *
 * Notion API 不吃 markdown，只吃 block 对象数组；读回来也是 block 数组。
 * 这个模块只做纯函数转换，不碰网络：
 *   - mdToBlocks(md)            markdown → block[]（写）
 *   - renderBlock(block, child) block + 已渲染的子块 → markdown 行（读）
 *   - richTextToMd(rich[])      rich_text → 带格式的 markdown 片段
 *
 * 两条 Notion 硬限制在这里兜住：单个 rich_text 内容 ≤ 2000 字符（超了自动切），
 * 单次请求 children ≤ 100 个（由 index.js 分批，常量在这里导出）。
 */

const MAX_TEXT = 2000; // 单个 rich_text 内容上限
export const MAX_CHILDREN = 100; // 单次请求 children 上限

/* ---------------- markdown → Notion ---------------- */

// 行内标记：顺序即优先级，** 必须排在 * 前面
const INLINE_RE =
  /(`[^`\n]+`)|(\[[^\]]*\]\([^)\s]+\))|(\*\*[^*\n]+\*\*)|(__[^_\n]+__)|(~~[^~\n]+~~)|(\*[^*\n]+\*)|(_[^_\n]+_)/g;

const LANGS = new Set([
  "abap", "arduino", "bash", "basic", "c", "clojure", "coffeescript", "c++", "c#", "css",
  "dart", "diff", "docker", "elixir", "elm", "erlang", "flow", "fortran", "f#", "gherkin",
  "glsl", "go", "graphql", "groovy", "haskell", "html", "java", "javascript", "json",
  "julia", "kotlin", "latex", "less", "lisp", "livescript", "lua", "makefile", "markdown",
  "markup", "matlab", "mermaid", "nix", "objective-c", "ocaml", "pascal", "perl", "php",
  "plain text", "powershell", "prolog", "protobuf", "python", "r", "reason", "ruby", "rust",
  "sass", "scala", "scheme", "scss", "shell", "sql", "swift", "typescript", "vb.net",
  "verilog", "vhdl", "visual basic", "webassembly", "xml", "yaml",
]);

const LANG_ALIAS = {
  js: "javascript", jsx: "javascript", ts: "typescript", tsx: "typescript",
  py: "python", py3: "python", sh: "shell", zsh: "shell", console: "shell",
  yml: "yaml", md: "markdown", cpp: "c++", cxx: "c++", cs: "c#", rb: "ruby",
  rs: "rust", golang: "go", kt: "kotlin", txt: "plain text", text: "plain text",
  "": "plain text",
};

function normLang(lang = "") {
  const l = String(lang).trim().toLowerCase();
  const mapped = LANG_ALIAS[l] ?? l;
  return LANGS.has(mapped) ? mapped : "plain text";
}

function textNode(content, annotations, link) {
  const node = { type: "text", text: { content } };
  if (link) node.text.link = { url: link };
  if (annotations) node.annotations = annotations;
  return node;
}

/** 超长内容切成多段，绕过 rich_text 2000 字符上限。 */
function chunk(nodes) {
  const out = [];
  for (const n of nodes) {
    let rest = n.text.content;
    if (rest.length <= MAX_TEXT) {
      out.push(n);
      continue;
    }
    while (rest.length) {
      out.push({ ...n, text: { ...n.text, content: rest.slice(0, MAX_TEXT) } });
      rest = rest.slice(MAX_TEXT);
    }
  }
  return out;
}

/** 解析行内格式（粗体/斜体/行内码/删除线/链接）→ rich_text[]。 */
export function parseInline(str) {
  const s = String(str ?? "");
  const out = [];
  let last = 0;
  let m;
  INLINE_RE.lastIndex = 0;
  while ((m = INLINE_RE.exec(s))) {
    if (m.index > last) out.push(textNode(s.slice(last, m.index)));
    const tok = m[0];
    if (tok.startsWith("`")) {
      out.push(textNode(tok.slice(1, -1), { code: true }));
    } else if (tok.startsWith("[")) {
      const sep = tok.lastIndexOf("](");
      const label = tok.slice(1, sep);
      const url = tok.slice(sep + 2, -1);
      out.push(textNode(label || url, null, url));
    } else if (tok.startsWith("**") || tok.startsWith("__")) {
      out.push(textNode(tok.slice(2, -2), { bold: true }));
    } else if (tok.startsWith("~~")) {
      out.push(textNode(tok.slice(2, -2), { strikethrough: true }));
    } else {
      out.push(textNode(tok.slice(1, -1), { italic: true }));
    }
    last = m.index + tok.length;
  }
  if (last < s.length) out.push(textNode(s.slice(last)));
  return chunk(out.filter((n) => n.text.content !== ""));
}

const block = (type, payload) => ({ object: "block", type, [type]: payload });

const LIST_TYPES = new Set(["bulleted_list_item", "numbered_list_item", "to_do", "toggle"]);

/** 去掉空的 children 数组（Notion 不接受空数组）。 */
function prune(blocks) {
  for (const b of blocks) {
    const body = b[b.type];
    if (!body || !Array.isArray(body.children)) continue;
    if (body.children.length === 0) delete body.children;
    else prune(body.children);
  }
  return blocks;
}

/**
 * markdown → Notion block[]。
 * 支持：标题(1-3，更深的降级为 h3)、无序/有序列表(按缩进嵌套)、任务列表、
 * 引用、代码块(带语言)、分割线、表格、段落(连续行合并)。
 */
export function mdToBlocks(md) {
  const lines = String(md ?? "").replace(/\r\n?/g, "\n").split("\n");
  const root = [];
  const stack = [{ indent: -1, children: root }]; // 列表缩进栈
  let para = [];

  const push = (b, indent = 0, isList = false) => {
    while (stack.length > 1 && indent <= stack[stack.length - 1].indent) stack.pop();
    stack[stack.length - 1].children.push(b);
    if (isList) {
      b[b.type].children = b[b.type].children || [];
      stack.push({ indent, children: b[b.type].children });
    } else {
      stack.length = 1; // 非列表块打断嵌套
    }
  };

  const flushPara = () => {
    if (!para.length) return;
    const text = para.join("\n");
    para = [];
    push(block("paragraph", { rich_text: parseInline(text) }));
  };

  const cellsOf = (row) =>
    row.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());

  for (let i = 0; i < lines.length; i++) {
    const raw = lines[i];
    const indent = (raw.match(/^[ \t]*/)[0] || "").replace(/\t/g, "  ").length;
    const t = raw.trim();

    // 代码块
    if (t.startsWith("```")) {
      flushPara();
      const lang = normLang(t.slice(3).trim());
      const buf = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith("```")) buf.push(lines[i]), i++;
      push(block("code", { language: lang, rich_text: chunk([textNode(buf.join("\n"))]) }));
      continue;
    }

    if (!t) {
      flushPara();
      continue;
    }

    let m;

    // 标题（Notion 只有 h1-h3）
    if ((m = t.match(/^(#{1,6})\s+(.*)$/))) {
      flushPara();
      const lvl = Math.min(m[1].length, 3);
      push(block(`heading_${lvl}`, { rich_text: parseInline(m[2]) }));
      continue;
    }

    // 分割线
    if (/^(-{3,}|_{3,}|\*{3,})$/.test(t)) {
      flushPara();
      push(block("divider", {}));
      continue;
    }

    // 表格：本行是 |...|，下一行是分隔行
    if (t.startsWith("|") && /^\|[\s:|-]+\|$/.test((lines[i + 1] || "").trim())) {
      flushPara();
      const rows = [cellsOf(t)];
      i += 2; // 跳过分隔行
      while (i < lines.length && lines[i].trim().startsWith("|")) rows.push(cellsOf(lines[i])), i++;
      i--;
      const width = Math.max(...rows.map((r) => r.length));
      push(
        block("table", {
          table_width: width,
          has_column_header: true,
          has_row_children: false,
          children: rows.slice(0, MAX_CHILDREN).map((r) =>
            block("table_row", {
              cells: Array.from({ length: width }, (_, k) => parseInline(r[k] ?? "")),
            })
          ),
        })
      );
      continue;
    }

    // 引用（连续行合并成一个块）
    if ((m = t.match(/^>\s?(.*)$/))) {
      flushPara();
      const buf = [m[1]];
      while (i + 1 < lines.length && /^\s*>\s?/.test(lines[i + 1])) {
        buf.push(lines[++i].trim().replace(/^>\s?/, ""));
      }
      push(block("quote", { rich_text: parseInline(buf.join("\n")) }));
      continue;
    }

    // 任务列表
    if ((m = t.match(/^[-*+]\s+\[([ xX])\]\s+(.*)$/))) {
      flushPara();
      push(
        block("to_do", { checked: m[1].toLowerCase() === "x", rich_text: parseInline(m[2]) }),
        indent,
        true
      );
      continue;
    }

    // 无序列表
    if ((m = t.match(/^[-*+]\s+(.*)$/))) {
      flushPara();
      push(block("bulleted_list_item", { rich_text: parseInline(m[1]) }), indent, true);
      continue;
    }

    // 有序列表
    if ((m = t.match(/^\d+[.)]\s+(.*)$/))) {
      flushPara();
      push(block("numbered_list_item", { rich_text: parseInline(m[1]) }), indent, true);
      continue;
    }

    para.push(t);
  }
  flushPara();
  return prune(root);
}

/** markdown → 单个块（update_block 用：只取第一个块的 rich_text）。 */
export function mdToSingleRichText(md) {
  const blocks = mdToBlocks(md);
  const first = blocks[0];
  const body = first ? first[first.type] : null;
  return body?.rich_text ?? parseInline(md);
}

/* ---------------- Notion → markdown ---------------- */

/** rich_text[] → 带格式的 markdown 片段。 */
export function richTextToMd(rich = []) {
  return (rich || [])
    .map((r) => {
      if (r.type === "equation") return `$${r.equation?.expression ?? r.plain_text ?? ""}$`;
      let s = r.plain_text ?? r.text?.content ?? "";
      const a = r.annotations || {};
      if (a.code) s = "`" + s + "`";
      if (a.bold) s = `**${s}**`;
      if (a.italic) s = `*${s}*`;
      if (a.strikethrough) s = `~~${s}~~`;
      const href = r.href || r.text?.link?.url;
      if (href) s = `[${s}](${href})`;
      return s;
    })
    .join("");
}

const fileUrl = (f) => f?.external?.url || f?.file?.url || "";
const indentAll = (s, pad = "  ") =>
  s ? "\n" + s.split("\n").map((l) => pad + l).join("\n") : "";

/**
 * 单个 block → markdown 行。childMd 是调用方递归渲染好的子块内容。
 * 表格特殊：它的子块（table_row）已渲染成行，这里补上表头分隔行。
 */
export function renderBlock(b, childMd = "") {
  const t = b.type;
  const body = b[t] || {};
  const rt = body.rich_text ? richTextToMd(body.rich_text) : "";

  switch (t) {
    case "paragraph":
      return rt + indentAll(childMd);
    case "heading_1":
      return `# ${rt}`;
    case "heading_2":
      return `## ${rt}`;
    case "heading_3":
      return `### ${rt}`;
    case "bulleted_list_item":
      return `- ${rt}` + indentAll(childMd);
    case "numbered_list_item":
      return `1. ${rt}` + indentAll(childMd);
    case "to_do":
      return `- [${body.checked ? "x" : " "}] ${rt}` + indentAll(childMd);
    case "toggle":
      return `- ${rt}` + indentAll(childMd);
    case "quote":
      return rt.split("\n").map((l) => `> ${l}`).join("\n") + indentAll(childMd);
    case "callout":
      return `> ${body.icon?.emoji ?? "💡"} ${rt}` + indentAll(childMd);
    case "code":
      return "```" + (body.language === "plain text" ? "" : body.language || "") + "\n" + rt + "\n```";
    case "divider":
      return "---";
    case "child_page":
      return `- 📄 ${body.title} \`${b.id}\``;
    case "child_database":
      return `- 🗂 ${body.title} \`${b.id}\``;
    case "image":
      return `![${richTextToMd(body.caption)}](${fileUrl(body)})`;
    case "video":
    case "file":
    case "pdf":
      return `[${richTextToMd(body.caption) || t}](${fileUrl(body)})`;
    case "bookmark":
    case "embed":
    case "link_preview":
      return `[${richTextToMd(body.caption) || body.url}](${body.url})`;
    case "equation":
      return `$$${body.expression}$$`;
    case "table_row":
      return `| ${(body.cells || []).map((c) => richTextToMd(c)).join(" | ")} |`;
    case "table": {
      const rows = childMd ? childMd.split("\n") : [];
      if (!rows.length) return "";
      const sep = `|${" --- |".repeat(body.table_width || rows[0].split("|").length - 2)}`;
      return [rows[0], sep, ...rows.slice(1)].join("\n");
    }
    case "table_of_contents":
    case "breadcrumb":
    case "unsupported":
      return "";
    default:
      return rt ? rt + indentAll(childMd) : `<!-- ${t} -->`;
  }
}
