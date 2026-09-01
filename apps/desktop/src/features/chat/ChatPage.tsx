// SPDX-License-Identifier: AGPL-3.0-or-later

import { useEffect, useRef, useState } from "react";
import type { ChatClient, ChatMessage, ChatSession } from "./client";
import { ChatMarkdown } from "./ChatMarkdown";
import { insertMention, mentionQueryAtCursor, uniqueMentionPaths } from "./mentionQuery";
import { toolCardLabel } from "./toolCard";
import type { IndexClient } from "../index/client";

interface ChatPageProps {
  chatClient: ChatClient;
  repositoryId: string | null;
  historyOpen: boolean;
  newChatRequest?: number;
  plannerName?: string | null;
  indexClient?: IndexClient;
  onOpenWorkspace: () => void;
  onOpenModels?: () => void;
}

export function ChatPage({
  chatClient,
  repositoryId,
  historyOpen,
  newChatRequest = 0,
  plannerName = null,
  indexClient,
  onOpenWorkspace,
  onOpenModels,
}: ChatPageProps) {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mentionPaths, setMentionPaths] = useState<string[]>([]);
  const inflightSessionId = useRef<string | null>(null);
  const threadRef = useRef<HTMLOListElement | null>(null);
  const composerRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    void chatClient.listSessions().then(async (items) => {
      if (cancelled) {
        return;
      }
      setSessions(items);
      const first = items[0];
      if (!first) {
        return;
      }
      setActiveId(first.id);
      const payload = await chatClient.getSession(first.id);
      if (!cancelled) {
        setMessages(payload.messages);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [chatClient]);

  useEffect(() => {
    if (!busy) {
      return;
    }
    const sessionId = inflightSessionId.current ?? activeId;
    if (!sessionId) {
      return;
    }
    let cancelled = false;
    const pull = () => {
      void chatClient.getSession(sessionId).then((payload) => {
        if (!cancelled && payload.messages.length > 0) {
          setMessages(payload.messages);
        }
      });
    };
    pull();
    const timer = window.setInterval(pull, 250);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [busy, chatClient, activeId]);

  useEffect(() => {
    if (newChatRequest === 0) {
      return;
    }
    void startNewChat();
  }, [newChatRequest]);

  useEffect(() => {
    const node = threadRef.current;
    if (node) {
      node.scrollTop = node.scrollHeight;
    }
  }, [messages, busy]);

  useEffect(() => {
    composerRef.current?.focus();
  }, [chatClient]);

  useEffect(() => {
    if (!indexClient || !repositoryId) {
      setMentionPaths([]);
      return;
    }
    const cursor = composerRef.current?.selectionStart ?? draft.length;
    const mention = mentionQueryAtCursor(draft, cursor);
    if (!mention || mention.query === "") {
      setMentionPaths([]);
      return;
    }
    let cancelled = false;
    void indexClient.search(repositoryId, mention.query).then(
      (hits) => {
        if (!cancelled) {
          setMentionPaths(uniqueMentionPaths(hits).slice(0, 8));
        }
      },
      () => {
        if (!cancelled) {
          setMentionPaths([]);
        }
      },
    );
    return () => {
      cancelled = true;
    };
  }, [draft, indexClient, repositoryId]);

  async function ensureSession(): Promise<string> {
    if (activeId) {
      return activeId;
    }
    const created = await chatClient.createSession({ repositoryId });
    setSessions((current) => [created, ...current]);
    setActiveId(created.id);
    return created.id;
  }

  async function startNewChat(): Promise<void> {
    const created = await chatClient.createSession({ repositoryId });
    setSessions((current) => [created, ...current]);
    setActiveId(created.id);
    setMessages([]);
    setDraft("");
    setError(null);
    setMentionPaths([]);
  }

  async function onSend() {
    const text = draft.trim();
    if (text === "" || busy) {
      return;
    }
    const pending: ChatMessage = {
      id: `local_${Date.now()}`,
      role: "user",
      content: text,
      toolName: null,
      toolStatus: null,
    };
    setBusy(true);
    setError(null);
    setDraft("");
    setMentionPaths([]);
    setMessages((current) => [...current, pending]);
    if (activeId) {
      inflightSessionId.current = activeId;
    }
    try {
      const id = await ensureSession();
      inflightSessionId.current = id;
      const result = await chatClient.sendMessage(id, text, repositoryId);
      setMessages(result.messages);
      const listed = await chatClient.listSessions();
      setSessions(listed);
    } catch {
      setMessages((current) => current.filter((item) => item.id !== pending.id));
      setDraft(text);
      setError("Could not send that message. Check the model connection and try again.");
    } finally {
      inflightSessionId.current = null;
      setBusy(false);
    }
  }

  function applyMention(path: string): void {
    const cursor = composerRef.current?.selectionStart ?? draft.length;
    const mention = mentionQueryAtCursor(draft, cursor);
    if (!mention) {
      return;
    }
    const next = insertMention(draft, mention.start, mention.query, path);
    setDraft(next);
    setMentionPaths([]);
    requestAnimationFrame(() => {
      const node = composerRef.current;
      if (!node) {
        return;
      }
      const caret = mention.start + 1 + path.length + 1;
      node.focus();
      node.setSelectionRange(caret, caret);
      node.style.height = "auto";
      node.style.height = `${Math.min(200, Math.max(44, node.scrollHeight))}px`;
    });
  }

  async function onStop() {
    const id = inflightSessionId.current ?? activeId;
    if (!id) {
      setBusy(false);
      return;
    }
    try {
      await chatClient.cancelTurn(id);
      const payload = await chatClient.getSession(id);
      setMessages(payload.messages);
    } catch {
      setError("Could not stop this turn. Wait for it to finish, then try again.");
    }
  }

  return (
    <div className="chat-layout">
      {historyOpen ? (
        <aside className="chat-history" aria-label="Chat history">
          <button type="button" className="btn-quiet" onClick={() => void startNewChat()}>
            New chat
          </button>
          <ul className="chat-history__list">
            {sessions.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  className="chat-history__item"
                  aria-current={item.id === activeId ? "true" : undefined}
                  onClick={() => {
                    setActiveId(item.id);
                    void chatClient.getSession(item.id).then((payload) => {
                      setMessages(payload.messages);
                    });
                  }}
                >
                  {item.title}
                </button>
              </li>
            ))}
          </ul>
        </aside>
      ) : null}
      <section className="chat-stage">
        {messages.length === 0 ? (
          <div className="chat-empty">
            <h1 className="chat-empty__title">Ask Kronos</h1>
            <p>
              {repositoryId
                ? "Chat can search this workspace, read files, and start a longer goal when you want unattended work."
                : "You can ask how Kronos works now. Open a git folder to index code."}
            </p>
            {repositoryId ? null : (
              <button type="button" className="btn-quiet" onClick={onOpenWorkspace}>
                Open folder
              </button>
            )}
          </div>
        ) : (
          <ol className="chat-thread" ref={threadRef} aria-live="polite">
            {messages.map((item) => (
              <li
                key={item.id}
                className={`chat-bubble chat-bubble--${item.role}${item.toolStatus === "streaming" ? " chat-bubble--streaming" : ""}`}
                data-tool={item.toolName ?? undefined}
              >
                {item.role === "tool" ? (
                  <p className="chat-bubble__tool">{toolCardLabel(item.toolName, item.toolStatus)}</p>
                ) : null}
                {item.role === "assistant" ? (
                  <ChatMarkdown source={item.content} />
                ) : (
                  <p>{item.content}</p>
                )}
              </li>
            ))}
          </ol>
        )}
        {busy ? (
          <p className="chat-turn-status" aria-live="polite">
            Working on this turn.
          </p>
        ) : null}
        {error ? <p className="wizard__error">{error}</p> : null}
        <div className="chat-composer-wrap">
          {mentionPaths.length > 0 ? (
            <ul className="chat-mentions" id="chat-mentions" role="listbox" aria-label="Workspace files">
              {mentionPaths.map((path) => (
                <li key={path} role="presentation">
                  <button
                    type="button"
                    className="chat-mentions__item"
                    role="option"
                    title={path}
                    onMouseDown={(event) => {
                      event.preventDefault();
                      applyMention(path);
                    }}
                  >
                    {path}
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
          <label className="chat-composer">
            <span className="visually-hidden">Ask Kronos</span>
            <textarea
              ref={composerRef}
              className="chat-composer__input"
              value={draft}
              placeholder={repositoryId ? "Ask Kronos. Type @ to mention a file." : "Ask Kronos"}
              aria-label="Ask Kronos"
              aria-autocomplete="list"
              aria-expanded={mentionPaths.length > 0}
              aria-controls={mentionPaths.length > 0 ? "chat-mentions" : undefined}
              rows={2}
              onChange={(event) => {
                setDraft(event.target.value);
                const node = event.target;
                node.style.height = "auto";
                node.style.height = `${Math.min(200, Math.max(44, node.scrollHeight))}px`;
              }}
              onKeyDown={(event) => {
                if (event.key === "Escape" && mentionPaths.length > 0) {
                  event.preventDefault();
                  setMentionPaths([]);
                  return;
                }
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  const firstPath = mentionPaths[0];
                  if (firstPath) {
                    applyMention(firstPath);
                    return;
                  }
                  void onSend();
                }
              }}
            />
            <span className="chat-composer__toolbar">
              {plannerName ? (
                onOpenModels ? (
                  <button type="button" className="chat-composer__model" onClick={onOpenModels}>
                    {plannerName}
                  </button>
                ) : (
                  <span className="chat-composer__model">{plannerName}</span>
                )
              ) : null}
              <button
                type="button"
                className={busy ? "btn-quiet" : "btn-primary"}
                disabled={busy || draft.trim() === ""}
                onClick={() => void onSend()}
              >
                {busy ? "Working" : "Send"}
              </button>
              {busy ? (
                <button type="button" className="btn-primary" onClick={() => void onStop()}>
                  Stop
                </button>
              ) : null}
            </span>
          </label>
        </div>
      </section>
    </div>
  );
}
