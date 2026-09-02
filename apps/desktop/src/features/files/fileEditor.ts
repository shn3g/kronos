// SPDX-License-Identifier: AGPL-3.0-or-later

export const SAVE_FILE_EVENT = "kronos-save-file";
export const FIND_IN_FILE_EVENT = "kronos-find-in-file";
export const FIND_IN_FILES_EVENT = "kronos-find-in-files";
export const REPLACE_IN_FILE_EVENT = "kronos-replace-in-file";
export const GO_TO_LINE_EVENT = "kronos-go-to-line";
export const ASK_IN_CHAT_EVENT = "kronos-ask-in-chat";
export const WORKSPACE_SEARCH_SNIPPET_LIMIT = 120;
export const MAX_ASK_IN_CHAT_SELECTION = 4000;

export interface AskInChatSelection {
  text: string;
  startLine: number;
  endLine: number;
}

export interface FileFindMatch {
  start: number;
  end: number;
}

export interface FileFindOptions {
  caseSensitive?: boolean;
  wholeWord?: boolean;
  regularExpression?: boolean;
}

const MAX_FIND_MATCHES = 10_000;

export function fileDraftIsDirty(saved: string | null, draft: string | null): boolean {
  if (saved === null || draft === null) {
    return false;
  }
  return saved !== draft;
}

export const EDITOR_INDENT = "  ";

export function insertEditorText(
  content: string,
  start: number,
  end: number,
  insertion: string,
): { content: string; caret: number } {
  const from = Math.max(0, Math.min(start, content.length));
  const to = Math.max(from, Math.min(end, content.length));
  return {
    content: `${content.slice(0, from)}${insertion}${content.slice(to)}`,
    caret: from + insertion.length,
  };
}

export function applyEditorTab(
  content: string,
  start: number,
  end: number,
  shift: boolean,
): { content: string; start: number; end: number } {
  if (shift) {
    return outdentEditorLines(content, start, end);
  }
  if (start === end) {
    const next = insertEditorText(content, start, end, EDITOR_INDENT);
    return { content: next.content, start: next.caret, end: next.caret };
  }
  return indentEditorLines(content, start, end);
}

function indentEditorLines(
  content: string,
  start: number,
  end: number,
): { content: string; start: number; end: number } {
  return rewriteEditorLines(content, start, end, (line) => `${EDITOR_INDENT}${line}`);
}

function outdentEditorLines(
  content: string,
  start: number,
  end: number,
): { content: string; start: number; end: number } {
  return rewriteEditorLines(content, start, end, (line) => {
    if (line.startsWith(EDITOR_INDENT)) {
      return line.slice(EDITOR_INDENT.length);
    }
    if (line.startsWith("\t")) {
      return line.slice(1);
    }
    if (line.startsWith(" ")) {
      return line.slice(1);
    }
    return line;
  });
}

function rewriteEditorLines(
  content: string,
  start: number,
  end: number,
  rewrite: (line: string) => string,
): { content: string; start: number; end: number } {
  const from = Math.max(0, Math.min(start, end, content.length));
  const to = Math.max(0, Math.min(Math.max(start, end), content.length));
  const last = from === to ? from : Math.max(from, to - 1);
  const blockStart = lineStartAt(content, from);
  const blockEnd = lineEndExclusive(content, last);
  const block = content.slice(blockStart, blockEnd);
  const lines = block.split("\n");
  const nextLines = lines.map((line) => rewrite(line));
  const nextBlock = nextLines.join("\n");
  const nextContent = `${content.slice(0, blockStart)}${nextBlock}${content.slice(blockEnd)}`;
  let deltaBefore = 0;
  let deltaInside = 0;
  let walked = blockStart;
  for (let index = 0; index < lines.length; index += 1) {
    const original = lines[index] ?? "";
    const next = nextLines[index] ?? "";
    const change = next.length - original.length;
    const lineStart = walked;
    if (lineStart < from) {
      deltaBefore += change;
    }
    if (lineStart < to) {
      deltaInside += change;
    }
    walked += original.length + 1;
  }
  return {
    content: nextContent,
    start: Math.max(0, from + deltaBefore),
    end: Math.max(0, to + deltaInside),
  };
}

function lineStartAt(content: string, offset: number): number {
  const clamped = Math.max(0, Math.min(offset, content.length));
  const newline = content.lastIndexOf("\n", Math.max(0, clamped - 1));
  if (newline < 0) {
    return 0;
  }
  return newline + 1;
}

function lineEndExclusive(content: string, offset: number): number {
  const clamped = Math.max(0, Math.min(offset, content.length));
  const newline = content.indexOf("\n", clamped);
  if (newline < 0) {
    return content.length;
  }
  return newline;
}

export function editorLineLabels(content: string): string[] {
  const count = content.split("\n").length;
  return Array.from({ length: Math.max(1, count) }, (_, index) => String(index + 1));
}

export function findInFileText(
  content: string,
  query: string,
  options: FileFindOptions = {},
): FileFindMatch[] {
  const pattern = compileFindPattern(query, options);
  if (pattern === null) {
    return [];
  }
  const matches: FileFindMatch[] = [];
  for (const match of content.matchAll(pattern)) {
    if (match.index === undefined || match[0] === "") {
      continue;
    }
    matches.push({ start: match.index, end: match.index + match[0].length });
    if (matches.length >= MAX_FIND_MATCHES) {
      break;
    }
  }
  return matches;
}

export function fileFindQueryError(query: string, options: FileFindOptions = {}): string | null {
  if (options.regularExpression !== true || query.trim() === "") {
    return null;
  }
  if (compileFindPattern(query, options) === null) {
    return "That regular expression is not valid.";
  }
  return null;
}

export function nextFileFindIndex(current: number, delta: number, length: number): number {
  if (length <= 0) {
    return 0;
  }
  return (current + delta + length) % length;
}

export function fileFindStatusLabel(query: string, matchCount: number, activeIndex: number): string {
  if (query.trim() === "") {
    return "";
  }
  if (matchCount <= 0) {
    return "No matches.";
  }
  return `${activeIndex + 1} of ${matchCount}`;
}

export function replaceInFileMatch(
  content: string,
  match: FileFindMatch,
  replacement: string,
): { content: string; caret: number } {
  if (match.start < 0 || match.end < match.start || match.end > content.length) {
    return { content, caret: content.length };
  }
  return {
    content: `${content.slice(0, match.start)}${replacement}${content.slice(match.end)}`,
    caret: match.start + replacement.length,
  };
}

export function replaceAllInFileText(
  content: string,
  query: string,
  replacement: string,
  options: FileFindOptions = {},
): { content: string; count: number } {
  const matches = findInFileText(content, query, options);
  if (matches.length === 0) {
    return { content, count: 0 };
  }
  let next = "";
  let last = 0;
  for (const match of matches) {
    next += `${content.slice(last, match.start)}${replacement}`;
    last = match.end;
  }
  return { content: `${next}${content.slice(last)}`, count: matches.length };
}

export interface GoToLineTarget {
  line: number;
  column: number | null;
}

export function parseGoToLineInput(raw: string): GoToLineTarget | null {
  const trimmed = raw.trim();
  const match = /^(\d+)(?:[:.,](\d+))?$/.exec(trimmed);
  if (match === null) {
    return null;
  }
  const line = Number(match[1]);
  if (!Number.isInteger(line) || line < 1) {
    return null;
  }
  if (match[2] === undefined) {
    return { line, column: null };
  }
  const column = Number(match[2]);
  if (!Number.isInteger(column) || column < 1) {
    return null;
  }
  return { line, column };
}

export function askInChatSelection(
  content: string,
  start: number,
  end: number,
): AskInChatSelection | null {
  const from = Math.max(0, Math.min(start, end, content.length));
  const to = Math.max(0, Math.min(Math.max(start, end), content.length));
  if (from === to) {
    return null;
  }
  const raw = content.slice(from, to);
  if (raw.trim() === "") {
    return null;
  }
  const text =
    raw.length > MAX_ASK_IN_CHAT_SELECTION ? raw.slice(0, MAX_ASK_IN_CHAT_SELECTION) : raw;
  return {
    text,
    startLine: lineNumberAt(content, from),
    endLine: lineNumberAt(content, to),
  };
}

function lineNumberAt(content: string, offset: number): number {
  const clamped = Math.max(0, Math.min(offset, content.length));
  if (clamped === 0) {
    return 1;
  }
  return content.slice(0, clamped).split("\n").length;
}

export function selectionForLineColumn(
  content: string,
  line: number,
  column: number | null,
): { start: number; end: number; line: number } {
  const lines = content.split("\n");
  const last = Math.max(1, lines.length);
  const target = Math.min(Math.max(Math.trunc(line), 1), last);
  let offset = 0;
  for (let index = 0; index < target - 1; index += 1) {
    offset += (lines[index] ?? "").length + 1;
  }
  const text = lines[target - 1] ?? "";
  if (column === null) {
    return { start: offset, end: offset + text.length, line: target };
  }
  const col = Math.min(Math.max(Math.trunc(column), 1), text.length + 1);
  const caret = offset + (col - 1);
  return { start: caret, end: caret, line: target };
}

export function goToLineStatusLabel(line: number, lineCount: number): string {
  return `Line ${line} of ${lineCount}`;
}

export function workspaceSearchHitLabel(path: string, startLine: number): string {
  const safe = path.trim();
  if (safe === "") {
    return "";
  }
  const line = Number.isInteger(startLine) && startLine > 0 ? startLine : 1;
  return `${safe}:${line}`;
}

export function workspaceSearchHitSnippet(text: string): string {
  const line = text.replace(/\s+/g, " ").trim();
  if (line.length <= WORKSPACE_SEARCH_SNIPPET_LIMIT) {
    return line;
  }
  return `${line.slice(0, WORKSPACE_SEARCH_SNIPPET_LIMIT - 3)}...`;
}

function compileFindPattern(query: string, options: FileFindOptions): RegExp | null {
  const trimmed = query.trim();
  if (trimmed === "") {
    return null;
  }
  const source = options.regularExpression === true ? trimmed : escapeRegExp(trimmed);
  const wrapped = options.wholeWord === true ? `\\b(?:${source})\\b` : source;
  const flags = options.caseSensitive === true ? "g" : "gi";
  try {
    return new RegExp(wrapped, flags);
  } catch {
    return null;
  }
}

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
