// SPDX-License-Identifier: AGPL-3.0-or-later

import { useEffect, useMemo, useRef, useState } from "react";
import type { EngineClient } from "../../engine/client";
import {
  createProductionRepositoriesClient,
  type EnrolledRepository,
} from "../workspaces/client";
import {
  createProductionChatClient,
  type ChatClient,
  type ChatMessage,
  type ConversationSummary,
  type GoalSnippet,
} from "./client";

export type { ChatClient } from "./client";

export interface ChatPageClients extends ChatClient {
  listRepositories(): Promise<EnrolledRepository[]>;
}

interface ChatPageProps {
  engineClient: EngineClient;
  chatClient?: ChatPageClients;
}

type AssistantBlock =
  | { type: "paragraph"; text: string }
  | { type: "code"; language: string; text: string };

const productionChat = createProductionChatClient();
const productionRepos = createProductionRepositoriesClient();
const productionPageClient: ChatPageClients = {
  ...productionChat,
  listRepositories: () => productionRepos.list(),
};

export function ChatPage({ engineClient, chatClient }: ChatPageProps) {
  const client = chatClient ?? productionPageClient;
  const [ready, setReady] = useState(false);
  const [repositories, setRepositories] = useState<EnrolledRepository[]>([]);
  const [selectedRepoId, setSelectedRepoId] = useState("");
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [selectedConvId, setSelectedConvId] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [goalStates, setGoalStates] = useState<Record<string, GoalSnippet>>({});
  const requestIdRef = useRef<string | null>(null);
  const selectedConvRef = useRef(selectedConvId);
  selectedConvRef.current = selectedConvId;
  const loadGenerationRef = useRef(0);
  const skipReloadForConvRef = useRef<string | null>(null);

  const goalIds = useMemo(() => {
    const ids = new Set<string>();
    for (const message of messages) {
      for (const id of message.goalRefs) {
        ids.add(id);
      }
    }
    return [...ids];
  }, [messages]);

  useEffect(() => {
    let cancelled = false;
    const apply = () => {
      void engineClient.getState().then((state) => {
        if (!cancelled) {
          setReady(state.status === "ready");
        }
      });
    };
    apply();
    const interval = window.setInterval(apply, 1500);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [engineClient]);

  useEffect(() => {
    if (!ready) {
      return;
    }
    let cancelled = false;
    void client.listRepositories().then((items) => {
      if (cancelled) {
        return;
      }
      setRepositories(items);
      setSelectedRepoId((current) => current || items[0]?.id || "");
    });
    return () => {
      cancelled = true;
    };
  }, [client, ready]);

  useEffect(() => {
    if (!ready || !selectedRepoId) {
      return;
    }
    let cancelled = false;
    void client.listConversations(selectedRepoId).then((items) => {
      if (cancelled) {
        return;
      }
      setConversations(items);
      setSelectedConvId((current) => {
        if (current && items.some((item) => item.id === current)) {
          return current;
        }
        return items[0]?.id || "";
      });
    });
    return () => {
      cancelled = true;
    };
  }, [client, ready, selectedRepoId]);

  useEffect(() => {
    if (!ready || !selectedConvId) {
      return;
    }
    const generation = loadGenerationRef.current;
    const convId = selectedConvId;
    let cancelled = false;
    void client.getConversation(convId).then((detail) => {
      if (cancelled || selectedConvRef.current !== convId) {
        return;
      }
      if (loadGenerationRef.current !== generation) {
        return;
      }
      if (skipReloadForConvRef.current === convId) {
        return;
      }
      setMessages(detail.messages);
    });
    return () => {
      cancelled = true;
    };
  }, [client, ready, selectedConvId]);

  useEffect(() => {
    if (!ready || goalIds.length === 0) {
      return;
    }
    let cancelled = false;
    const refresh = () => {
      void Promise.all(goalIds.map((id) => client.getGoal(id))).then((snippets) => {
        if (cancelled) {
          return;
        }
        setGoalStates((current) => {
          const next = { ...current };
          for (const snippet of snippets) {
            next[snippet.id] = snippet;
          }
          return next;
        });
      });
    };
    refresh();
    const interval = window.setInterval(refresh, 1500);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [client, ready, goalIds]);

  if (!ready) {
    return (
      <section className="chat-page">
        <p className="page-kicker">Chat</p>
        <h1 className="page-title">Chat</h1>
        <p className="page-body">
          Connect a compatible engine to chat with the orchestrator. Replies stay closed until the
          local engine is ready.
        </p>
      </section>
    );
  }

  function allowConversationReload() {
    skipReloadForConvRef.current = null;
    loadGenerationRef.current += 1;
  }

  async function onNewConversation() {
    if (!selectedRepoId) {
      return;
    }
    setError(null);
    try {
      const created = await client.createConversation(selectedRepoId);
      allowConversationReload();
      setConversations((current) => [created, ...current]);
      setSelectedConvId(created.id);
      setMessages([]);
    } catch {
      setError("Could not create a conversation.");
    }
  }

  async function onDeleteConversation() {
    if (!selectedConvId) {
      return;
    }
    const id = selectedConvId;
    setError(null);
    try {
      await client.deleteConversation(id);
      allowConversationReload();
      const remaining = conversations.filter((item) => item.id !== id);
      setConversations(remaining);
      const nextId = remaining[0]?.id || "";
      setSelectedConvId(nextId);
      if (!nextId) {
        setMessages([]);
      }
    } catch {
      setError("Could not delete the conversation.");
    }
  }

  async function onSend() {
    const content = draft.trim();
    if (!content || streaming) {
      return;
    }
    let conversationId = selectedConvId;
    if (!conversationId) {
      if (!selectedRepoId) {
        return;
      }
      try {
        const created = await client.createConversation(selectedRepoId);
        conversationId = created.id;
        setConversations((current) => [created, ...current]);
        setSelectedConvId(created.id);
      } catch {
        setError("Could not create a conversation.");
        return;
      }
    }
    const requestId = crypto.randomUUID();
    requestIdRef.current = requestId;
    skipReloadForConvRef.current = conversationId;
    loadGenerationRef.current += 1;
    const userMessage: ChatMessage = {
      id: `local-user-${requestId}`,
      role: "user",
      content,
      citations: [],
      goalRefs: [],
    };
    const assistantMessage: ChatMessage = {
      id: `local-asst-${requestId}`,
      role: "assistant",
      content: "",
      citations: [],
      goalRefs: [],
    };
    setDraft("");
    setError(null);
    setStreaming(true);
    setMessages((current) => [...current, userMessage, assistantMessage]);
    try {
      await client.streamMessage(conversationId, content, {
        requestId,
        onDelta: (delta) => {
          setMessages((current) =>
            current.map((item) =>
              item.id === assistantMessage.id ? { ...item, content: item.content + delta } : item,
            ),
          );
        },
        onDone: (result) => {
          setMessages((current) =>
            current.map((item) =>
              item.id === assistantMessage.id
                ? {
                    ...item,
                    content: result.content || item.content,
                    citations: result.citations,
                    goalRefs: result.goalRefs,
                  }
                : item,
            ),
          );
        },
        onError: (message) => {
          setError(message);
          setMessages((current) =>
            current.filter((item) => item.id !== assistantMessage.id || item.content.length > 0),
          );
        },
      });
    } finally {
      setStreaming(false);
      requestIdRef.current = null;
    }
  }

  async function onStop() {
    const requestId = requestIdRef.current;
    if (!requestId) {
      return;
    }
    await client.cancelStream(requestId);
  }

  const selectedConversation = conversations.find((item) => item.id === selectedConvId) ?? null;

  return (
    <section className="chat-page">
      <p className="page-kicker">Chat</p>
      <h1 className="page-title">Chat</h1>
      <p className="page-body">
        The orchestrator answers cheap questions itself and turns real work into goals. Prefix a
        message with /goal to delegate.
      </p>
      <div className="chat-page__toolbar">
        {repositories.length ? (
          <label className="index-page__field" htmlFor="chat-repo">
            Repository
            <select
              id="chat-repo"
              value={selectedRepoId}
              onChange={(event) => {
                allowConversationReload();
                setSelectedRepoId(event.target.value);
                setSelectedConvId("");
                setMessages([]);
              }}
            >
              {repositories.map((repo) => (
                <option key={repo.id} value={repo.id}>
                  {repo.displayName}
                </option>
              ))}
            </select>
          </label>
        ) : (
          <p className="index-page__empty">Enrol a repository before chatting.</p>
        )}
        <div className="chat-page__toolbar-actions">
          <button type="button" className="btn-quiet" onClick={() => void onNewConversation()}>
            New conversation
          </button>
          <button
            type="button"
            className="btn-quiet"
            onClick={() => void onDeleteConversation()}
            disabled={!selectedConvId}
          >
            Delete
          </button>
        </div>
      </div>
      <div className="chat-page__layout">
        <aside className="chat-page__sidebar">
          {conversations.length ? (
            <ul className="chat-page__conversations">
              {conversations.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    className="workspace-card"
                    aria-current={item.id === selectedConvId ? "true" : undefined}
                    onClick={() => {
                      if (skipReloadForConvRef.current !== item.id) {
                        allowConversationReload();
                      }
                      setSelectedConvId(item.id);
                    }}
                  >
                    <p className="workspace-card__name">{item.title}</p>
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="index-page__empty">No conversations yet.</p>
          )}
        </aside>
        <div className="chat-page__main">
          <div className="chat-page__thread" aria-live="polite">
            {messages.length === 0 ? (
              <p className="index-page__empty">
                {selectedConversation
                  ? "Send a message to start this thread."
                  : "Create a conversation or send a message."}{" "}
                Need a model? <a href="#/models">Models</a>
              </p>
            ) : (
              messages.map((message) => (
                <article
                  key={message.id}
                  className="chat-page__bubble"
                  data-role={message.role}
                >
                  <p className="chat-page__role">{message.role}</p>
                  {message.role === "assistant" ? (
                    <AssistantBody content={message.content} />
                  ) : (
                    <p className="chat-page__text">{message.content}</p>
                  )}
                  {message.citations.length ? (
                    <ul className="chat-page__citations">
                      {message.citations.map((citation) => (
                        <li key={`${citation.path}:${citation.startLine}`}>
                          <span className="chat-page__chip">
                            {citation.path}:{citation.startLine}
                          </span>
                        </li>
                      ))}
                    </ul>
                  ) : null}
                  {message.goalRefs.map((id) => {
                    const goal = goalStates[id];
                    return (
                      <article key={id} className="chat-page__goal-card">
                        <p className="workspace-card__name">{id}</p>
                        <p className="workspace-card__meta">{goal?.state ?? "loading"}</p>
                        {goal?.title ? (
                          <p className="workspace-card__status">{goal.title}</p>
                        ) : null}
                        <a href="#/goals">Goals</a>
                      </article>
                    );
                  })}
                </article>
              ))
            )}
          </div>
          {error ? (
            <p className="wizard__error">
              {error}{" "}
              <a href="#/models">Models</a>
            </p>
          ) : null}
          <form
            className="chat-page__composer"
            onSubmit={(event) => {
              event.preventDefault();
              void onSend();
            }}
          >
            <label className="index-page__field" htmlFor="chat-message">
              Message
              <textarea
                id="chat-message"
                className="wizard__input"
                value={draft}
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
            </label>
            {streaming ? (
              <button type="button" className="btn-quiet" onClick={() => void onStop()}>
                Stop
              </button>
            ) : (
              <button type="submit" className="btn-primary" disabled={!draft.trim()}>
                Send
              </button>
            )}
          </form>
        </div>
      </div>
    </section>
  );
}

function AssistantBody({ content }: { content: string }) {
  const blocks = splitAssistantBlocks(content);
  if (blocks.length === 0) {
    return <p className="chat-page__text">{content}</p>;
  }
  return (
    <div className="chat-page__assistant-body">
      {blocks.map((block, index) =>
        block.type === "code" ? (
          <div key={`code-${index}`} className="chat-page__code">
            <button
              type="button"
              className="btn-quiet"
              onClick={() => {
                void navigator.clipboard?.writeText(block.text);
              }}
            >
              Copy
            </button>
            <pre>
              <code>{block.text}</code>
            </pre>
          </div>
        ) : (
          <p key={`p-${index}`} className="chat-page__text">
            {block.text}
          </p>
        ),
      )}
    </div>
  );
}

function splitAssistantBlocks(content: string): AssistantBlock[] {
  const blocks: AssistantBlock[] = [];
  const fence = /```([^\n]*)\n([\s\S]*?)```/g;
  let last = 0;
  let match = fence.exec(content);
  while (match) {
    const before = content.slice(last, match.index).trim();
    if (before) {
      for (const para of before.split(/\n\n+/)) {
        if (para.trim()) {
          blocks.push({ type: "paragraph", text: para.trim() });
        }
      }
    }
    blocks.push({
      type: "code",
      language: match[1]?.trim() ?? "",
      text: match[2] ?? "",
    });
    last = match.index + match[0].length;
    match = fence.exec(content);
  }
  const after = content.slice(last).trim();
  if (after) {
    for (const para of after.split(/\n\n+/)) {
      if (para.trim()) {
        blocks.push({ type: "paragraph", text: para.trim() });
      }
    }
  }
  return blocks;
}
