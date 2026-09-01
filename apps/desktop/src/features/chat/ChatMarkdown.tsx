// SPDX-License-Identifier: AGPL-3.0-or-later

import { useState } from "react";
import type { ChatMarkdownBlock, ChatMarkdownSpan } from "./renderChatMarkdown";
import { renderChatMarkdown } from "./renderChatMarkdown";
import { CopyTextButton } from "./CopyTextButton";

interface ChatMarkdownProps {
  source: string;
  onApply?: ((path: string, content: string) => Promise<void>) | undefined;
}

export function ChatMarkdown({ source, onApply }: ChatMarkdownProps) {
  const blocks = renderChatMarkdown(source);
  return (
    <div className="chat-md">
      {blocks.map((block, index) => (
        <MarkdownBlock key={blockKey(block, index)} block={block} onApply={onApply} />
      ))}
    </div>
  );
}

function MarkdownBlock({
  block,
  onApply,
}: {
  block: ChatMarkdownBlock;
  onApply?: ((path: string, content: string) => Promise<void>) | undefined;
}) {
  if (block.type === "code") {
    return <CodeBlock block={block} onApply={onApply} />;
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

function CodeBlock({
  block,
  onApply,
}: {
  block: Extract<ChatMarkdownBlock, { type: "code" }>;
  onApply?: ((path: string, content: string) => Promise<void>) | undefined;
}) {
  const [path, setPath] = useState(block.path);
  const [status, setStatus] = useState<"idle" | "need-path" | "applied" | "error">("idle");

  async function onApplyClick(): Promise<void> {
    const target = path.trim();
    if (target === "") {
      setStatus("need-path");
      return;
    }
    if (!onApply) {
      return;
    }
    try {
      await onApply(target, block.text);
      setStatus("applied");
    } catch {
      setStatus("error");
    }
  }

  return (
    <div className="chat-md__code">
      <div className="chat-md__code-bar">
        {block.language ? <span className="chat-md__lang">{block.language}</span> : <span />}
        {onApply ? (
          <input
            className="chat-md__path"
            value={path}
            aria-label="File path"
            placeholder="File path"
            spellCheck={false}
            onChange={(event) => {
              setPath(event.target.value);
              if (status === "need-path" && event.target.value.trim() !== "") {
                setStatus("idle");
              }
            }}
          />
        ) : null}
        {onApply ? (
          <button type="button" className="copy-text__btn" onClick={() => void onApplyClick()}>
            {status === "applied" ? "Applied" : "Apply"}
          </button>
        ) : null}
        <CopyTextButton text={block.text} idleLabel="Copy" />
      </div>
      {status === "need-path" ? (
        <p className="copy-text__error" role="status">
          Add a file path to apply this.
        </p>
      ) : null}
      {status === "error" ? (
        <p className="copy-text__error" role="status">
          Could not apply that file. Check the path and try again.
        </p>
      ) : null}
      <pre className="chat-md__pre">
        <code>{block.text}</code>
      </pre>
    </div>
  );
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
    return `code:${index}:${block.language}:${block.path}`;
  }
  if (block.type === "heading") {
    return `h:${index}:${block.level}`;
  }
  if (block.type === "list") {
    return `list:${index}:${block.ordered ? "ol" : "ul"}`;
  }
  return `p:${index}`;
}
