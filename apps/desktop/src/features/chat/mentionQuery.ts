// SPDX-License-Identifier: AGPL-3.0-or-later

export interface MentionQuery {
  start: number;
  query: string;
}

export function mentionQueryAtCursor(text: string, cursor: number): MentionQuery | null {
  if (cursor < 1 || cursor > text.length) {
    return null;
  }
  const before = text.slice(0, cursor);
  const at = before.lastIndexOf("@");
  if (at < 0) {
    return null;
  }
  const previous = at === 0 ? "" : before.slice(at - 1, at);
  if (previous !== "" && /[\w.]/.test(previous)) {
    return null;
  }
  const query = before.slice(at + 1);
  if (query.includes(" ") || query.includes("\n")) {
    return null;
  }
  return { start: at, query };
}

export function insertMention(text: string, start: number, query: string, path: string): string {
  return `${text.slice(0, start)}@${path} ${text.slice(start + 1 + query.length)}`;
}

export function appendMention(text: string, path: string): string {
  const posix = path.replaceAll("\\", "/").trim();
  if (posix === "") {
    return text;
  }
  const token = `@${posix}`;
  const parts = text.trim().split(/\s+/).filter((part) => part !== "");
  if (parts.includes(token)) {
    return `${parts.join(" ")} `;
  }
  if (parts.length === 0) {
    return `${token} `;
  }
  return `${parts.join(" ")} ${token} `;
}

export interface AskInChatExcerpt {
  text: string;
  startLine: number;
  endLine: number;
}

export function appendAskInChatDraft(
  text: string,
  path: string,
  selection: AskInChatExcerpt | null,
): string {
  const withPath = appendMention(text, path);
  if (selection === null || selection.text.trim() === "") {
    return withPath;
  }
  const range =
    selection.startLine === selection.endLine
      ? `line ${selection.startLine}`
      : `lines ${selection.startLine}-${selection.endLine}`;
  return `${withPath.trimEnd()}\n\nSelected ${range}:\n\`\`\`\n${selection.text}\n\`\`\`\n`;
}

export function excerptFromMentionRequest(request: {
  selectedText?: string;
  startLine?: number;
  endLine?: number;
}): AskInChatExcerpt | null {
  const text = request.selectedText ?? "";
  if (text.trim() === "") {
    return null;
  }
  const startLine = request.startLine !== undefined && request.startLine > 0 ? request.startLine : 1;
  const endLine =
    request.endLine !== undefined && request.endLine >= startLine ? request.endLine : startLine;
  return { text, startLine, endLine };
}

export function uniqueMentionPaths(hits: { path: string }[]): string[] {
  const seen = new Set<string>();
  const paths: string[] = [];
  for (const hit of hits) {
    if (hit.path === "" || seen.has(hit.path)) {
      continue;
    }
    seen.add(hit.path);
    paths.push(hit.path);
  }
  return paths;
}

export interface MentionSegment {
  kind: "text" | "path";
  value: string;
}

export function mentionSegments(text: string): MentionSegment[] {
  const segments: MentionSegment[] = [];
  let cursor = 0;
  const pattern = /(?<![\w.])@([A-Za-z0-9_./\\-]+)/g;
  for (const match of text.matchAll(pattern)) {
    const index = match.index ?? 0;
    const token = match[1];
    if (token === undefined) {
      continue;
    }
    if (index > cursor) {
      segments.push({ kind: "text", value: text.slice(cursor, index) });
    }
    segments.push({ kind: "path", value: token.replaceAll("\\", "/") });
    cursor = index + match[0].length;
  }
  if (cursor < text.length || segments.length === 0) {
    segments.push({ kind: "text", value: text.slice(cursor) });
  }
  return segments;
}
