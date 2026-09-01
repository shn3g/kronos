// SPDX-License-Identifier: AGPL-3.0-or-later

export type ChatMarkdownSpan =
  | { type: "text"; text: string }
  | { type: "strong"; text: string }
  | { type: "code"; text: string };

export type ChatMarkdownBlock =
  | { type: "paragraph"; spans: ChatMarkdownSpan[] }
  | { type: "heading"; level: 1 | 2 | 3 | 4 | 5 | 6; spans: ChatMarkdownSpan[] }
  | { type: "list"; ordered: boolean; items: ChatMarkdownSpan[][] }
  | { type: "code"; language: string; path: string; text: string };

const FENCE = /```([^\n]*)\n([\s\S]*?)```/g;
const INLINE = /(\*\*([^*]+)\*\*|`([^`]+)`)/g;
const HEADING = /^(#{1,6}) (.+)$/;
const UNORDERED = /^[-*] (.+)$/;
const ORDERED = /^\d+\. (.+)$/;

export function renderChatMarkdown(source: string): ChatMarkdownBlock[] {
  const blocks: ChatMarkdownBlock[] = [];
  let last = 0;
  const fence = new RegExp(FENCE.source, "g");
  let match = fence.exec(source);
  while (match !== null) {
    pushBlocks(blocks, source.slice(last, match.index));
    const info = parseFenceInfo(match[1] ?? "");
    blocks.push({
      type: "code",
      language: info.language,
      path: info.path,
      text: trimTrailingNewline(match[2] ?? ""),
    });
    last = match.index + match[0].length;
    match = fence.exec(source);
  }
  pushBlocks(blocks, source.slice(last));
  if (blocks.length === 0) {
    return [{ type: "paragraph", spans: [{ type: "text", text: source }] }];
  }
  return blocks;
}

function pushBlocks(blocks: ChatMarkdownBlock[], chunk: string): void {
  const parts = chunk.split(/\n{2,}/);
  for (const part of parts) {
    const text = part.replace(/^\n+/, "").replace(/\n+$/, "");
    if (text === "") {
      continue;
    }
    pushChunkLines(blocks, text.split("\n"));
  }
}

function pushChunkLines(blocks: ChatMarkdownBlock[], lines: string[]): void {
  let index = 0;
  while (index < lines.length) {
    const heading = HEADING.exec(lines[index] ?? "");
    if (heading) {
      const marks = heading[1] ?? "#";
      const level = Math.min(6, Math.max(1, marks.length)) as 1 | 2 | 3 | 4 | 5 | 6;
      blocks.push({
        type: "heading",
        level,
        spans: parseSpans(heading[2] ?? ""),
      });
      index += 1;
      continue;
    }
    const list = listItem(lines[index] ?? "");
    if (list) {
      const items: ChatMarkdownSpan[][] = [];
      const ordered = list.ordered;
      while (index < lines.length) {
        const item = listItem(lines[index] ?? "");
        if (!item || item.ordered !== ordered) {
          break;
        }
        items.push(parseSpans(item.text));
        index += 1;
      }
      blocks.push({ type: "list", ordered, items });
      continue;
    }
    const paragraph: string[] = [];
    while (index < lines.length) {
      const line = lines[index] ?? "";
      if (HEADING.test(line) || listItem(line)) {
        break;
      }
      paragraph.push(line);
      index += 1;
    }
    if (paragraph.length > 0) {
      blocks.push({ type: "paragraph", spans: parseSpans(paragraph.join("\n")) });
    }
  }
}

function listItem(line: string): { ordered: boolean; text: string } | null {
  const unordered = UNORDERED.exec(line);
  if (unordered) {
    return { ordered: false, text: unordered[1] ?? "" };
  }
  const ordered = ORDERED.exec(line);
  if (ordered) {
    return { ordered: true, text: ordered[1] ?? "" };
  }
  return null;
}

function parseSpans(text: string): ChatMarkdownSpan[] {
  const spans: ChatMarkdownSpan[] = [];
  const inline = new RegExp(INLINE.source, "g");
  let last = 0;
  let match = inline.exec(text);
  while (match !== null) {
    if (match.index > last) {
      spans.push({ type: "text", text: text.slice(last, match.index) });
    }
    if (match[2] !== undefined) {
      spans.push({ type: "strong", text: match[2] });
    } else {
      spans.push({ type: "code", text: match[3] ?? "" });
    }
    last = match.index + match[0].length;
    match = inline.exec(text);
  }
  if (last < text.length) {
    spans.push({ type: "text", text: text.slice(last) });
  }
  return spans.length > 0 ? spans : [{ type: "text", text }];
}

function trimTrailingNewline(text: string): string {
  return text.endsWith("\n") ? text.slice(0, -1) : text;
}

export function parseFenceInfo(info: string): { language: string; path: string } {
  const trimmed = info.trim().replace(/\\/g, "/");
  if (trimmed === "") {
    return { language: "", path: "" };
  }
  const colon = colonFence(trimmed);
  if (colon) {
    return colon;
  }
  const space = trimmed.indexOf(" ");
  if (space === -1) {
    if (looksLikePath(trimmed)) {
      return { language: "", path: safeRelPath(trimmed) };
    }
    return { language: trimmed, path: "" };
  }
  return {
    language: trimmed.slice(0, space),
    path: safeRelPath(trimmed.slice(space + 1).trim()),
  };
}

function colonFence(trimmed: string): { language: string; path: string } | null {
  const index = trimmed.indexOf(":");
  if (index <= 0) {
    return null;
  }
  const rest = trimmed.slice(index + 1);
  if (!looksLikePath(rest)) {
    return null;
  }
  return { language: trimmed.slice(0, index), path: safeRelPath(rest) };
}

function looksLikePath(value: string): boolean {
  const trimmed = value.trim();
  return trimmed.includes("/") || trimmed.includes(".");
}

function safeRelPath(value: string): string {
  const trimmed = value.trim().replace(/\\/g, "/").replace(/^\/+/, "");
  if (trimmed === "") {
    return "";
  }
  const parts = trimmed.split("/");
  if (parts.some((part) => part === "" || part === "." || part === ".." || part === ".git")) {
    return "";
  }
  return parts.join("/");
}
