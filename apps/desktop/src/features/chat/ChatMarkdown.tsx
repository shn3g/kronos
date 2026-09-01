// SPDX-License-Identifier: AGPL-3.0-or-later

import type { ChatMarkdownBlock } from "./renderChatMarkdown";
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
  return (
    <p>
      {block.spans.map((span, index) => {
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
      })}
    </p>
  );
}

function blockKey(block: ChatMarkdownBlock, index: number): string {
  if (block.type === "code") {
    return `code:${index}:${block.language}`;
  }
  return `p:${index}`;
}
