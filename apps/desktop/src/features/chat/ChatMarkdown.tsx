// SPDX-License-Identifier: AGPL-3.0-or-later

import type { ChatMarkdownBlock, ChatMarkdownSpan } from "./renderChatMarkdown";
import { renderChatMarkdown } from "./renderChatMarkdown";

interface ChatMarkdownProps {
  source: string;
}

export function ChatMarkdown({ source }: ChatMarkdownProps) {
  const blocks = renderChatMarkdown(source);
  return (
    <div className="chat-md">
      {blocks.map((block, index) => (
        <MarkdownBlock key={blockKey(block, index)} block={block} />
      ))}
    </div>
  );
}

function MarkdownBlock({ block }: { block: ChatMarkdownBlock }) {
  if (block.type === "code") {
    return (
      <pre className="chat-md__pre">
        <code>{block.text}</code>
      </pre>
    );
  }
  if (block.type === "heading") {
    const Tag = headingTag(block.level);
    return <Tag className="chat-md__h">{renderSpans(block.spans)}</Tag>;
  }
  if (block.type === "list") {
    const Tag = block.ordered ? "ol" : "ul";
    return (
      <Tag className="chat-md__list">
        {block.items.map((item, index) => (
          <li key={`li${index}`}>{renderSpans(item)}</li>
        ))}
      </Tag>
    );
  }
  return <p>{renderSpans(block.spans)}</p>;
}

function renderSpans(spans: ChatMarkdownSpan[]) {
  return spans.map((span, index) => {
    if (span.type === "strong") {
      return <strong key={`s${index}`}>{span.text}</strong>;
    }
    if (span.type === "code") {
      return (
        <code key={`c${index}`} className="chat-md__inline">
          {span.text}
        </code>
      );
    }
    return <span key={`t${index}`}>{span.text}</span>;
  });
}

function headingTag(level: 1 | 2 | 3 | 4 | 5 | 6): "h2" | "h3" | "h4" {
  if (level <= 1) {
    return "h2";
  }
  if (level === 2) {
    return "h3";
  }
  return "h4";
}

function blockKey(block: ChatMarkdownBlock, index: number): string {
  if (block.type === "code") {
    return `code:${index}:${block.language}`;
  }
  if (block.type === "heading") {
    return `h:${index}:${block.level}`;
  }
  if (block.type === "list") {
    return `list:${index}:${block.ordered ? "ol" : "ul"}`;
  }
  return `p:${index}`;
}
