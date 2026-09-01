// SPDX-License-Identifier: AGPL-3.0-or-later

import { useEffect, useRef, useState } from "react";
import type { ChatClient, ChatMessage, ChatSession } from "./client";
import { toolCardLabel } from "./toolCard";

interface ChatPageProps {
  chatClient: ChatClient;
  repositoryId: string | null;
  historyOpen: boolean;
  newChatRequest?: number;
  onOpenWorkspace: () => void;
}

export function ChatPage({
  chatClient,
  repositoryId,
  historyOpen,
  newChatRequest = 0,
  onOpenWorkspace,
}: ChatPageProps) {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inflightSessionId = useRef<string | null>(null);

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
    if (newChatRequest === 0) {
      return;
    }
    void startNewChat();
  }, [newChatRequest]);

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
    setMessages((current) => [...current, pending]);
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
          <ol className="chat-thread">
            {messages.map((item) => (
              <li
                key={item.id}
                className={`chat-bubble chat-bubble--${item.role}`}
                data-tool={item.toolName ?? undefined}
              >
                {item.role === "tool" ? (
                  <p className="chat-bubble__tool">{toolCardLabel(item.toolName, item.toolStatus)}</p>
                ) : null}
                <p>{item.content}</p>
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
        <label className="chat-composer">
          <span className="visually-hidden">Ask Kronos</span>
          <textarea
            className="chat-composer__input"
            value={draft}
            placeholder="Ask Kronos…"
            aria-label="Ask Kronos"
            rows={3}
            onChange={(event) => {
              setDraft(event.target.value);
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void onSend();
              }
            }}
          />
          <button type="button" className="btn-primary" disabled={busy} onClick={() => void onSend()}>
            {busy ? "Working" : "Send"}
          </button>
          {busy ? (
            <button type="button" className="btn-quiet" onClick={() => void onStop()}>
              Stop
            </button>
          ) : null}
        </label>
      </section>
    </div>
  );
}
