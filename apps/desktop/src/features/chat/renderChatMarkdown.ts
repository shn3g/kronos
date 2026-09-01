// SPDX-License-Identifier: AGPL-3.0-or-later

export type ChatMarkdownSpan =
  | { type: "text"; text: string }
  | { type: "strong"; text: string }
  | { type: "code"; text: string };

export type ChatMarkdownBlock =
  | { type: "paragraph"; spans: ChatMarkdownSpan[] }
  | { type: "code"; language: string; text: string };

const FENCE = /```(\w*)\n([\s\S]*?)```/g;
const INLINE = /(\*\*([^*]+)\*\*|`([^`]+)`)/g;

export function renderChatMarkdown(source: string): ChatMarkdownBlock[] {
  const blocks: ChatMarkdownBlock[] = [];
  let last = 0;
  const fence = new RegExp(FENCE.source, "g");
  let match = fence.exec(source);
  while (match !== null) {
    pushParagraphs(blocks, source.slice(last, match.index));
    blocks.push({
      type: "code",
      language: match[1] ?? "",
      text: trimTrailingNewline(match[2] ?? ""),
    });
    last = match.index + match[0].length;
    match = fence.exec(source);
  }
  pushParagraphs(blocks, source.slice(last));
  if (blocks.length === 0) {
    return [{ type: "paragraph", spans: [{ type: "text", text: source }] }];
  }
  return blocks;
}

function pushParagraphs(blocks: ChatMarkdownBlock[], chunk: string): void {
  const parts = chunk.split(/\n{2,}/);
  for (const part of parts) {
    const text = part.replace(/^\n+/, "").replace(/\n+$/, "");
    if (text === "") {
      continue;
    }
    blocks.push({ type: "paragraph", spans: parseSpans(text) });
  }
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
