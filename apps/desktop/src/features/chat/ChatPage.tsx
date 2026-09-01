// SPDX-License-Identifier: AGPL-3.0-or-later

import { useEffect, useRef, useState, type ClipboardEvent, type DragEvent } from "react";
import type { ChatClient, ChatMessage, ChatSession } from "./client";
import { ChatMarkdown } from "./ChatMarkdown";
import { ChatPathButton } from "./ChatPathButton";
import { chatContextMeterLabel, chatContextUsage, chatContextWarning } from "./contextMeter";
import { CopyTextButton } from "./CopyTextButton";
import { appendAskInChatDraft, excerptFromMentionRequest, insertMention, mentionQueryAtCursor, mentionSegments, uniqueMentionPaths } from "./mentionQuery";
import {
  MAX_CHAT_IMAGES_PER_TURN,
  clipboardHasFiles,
  dataUrlForChatImage,
  imageFilesFromClipboard,
  pastedImageError,
  readPastedImageFile,
  userMessageSegments,
  type ChatComposerImage,
} from "./pastedImage";
import { toolCardLabel } from "./toolCard";
import type { IndexClient } from "../index/client";
import { safeWorkspaceRelPath } from "../files/workspacePath";

const EMPTY_MENTION_REQUEST = { path: "", nonce: 0, selectedText: "", startLine: 0, endLine: 0 };

interface ChatMentionRequest {
  path: string;
  nonce: number;
  selectedText?: string;
  startLine?: number;
  endLine?: number;
}

interface ChatPageProps {
  chatClient: ChatClient;
  repositoryId: string | null;
  historyOpen: boolean;
  newChatRequest?: number;
  mentionRequest?: ChatMentionRequest;
  plannerName?: string | null;
  indexClient?: IndexClient;
  onOpenWorkspace: () => void;
  onOpenModels?: () => void;
  onApplyFile?: ((path: string, content: string) => Promise<void>) | undefined;
  onOpenPath?: ((path: string) => void) | undefined;
}

export function ChatPage({
  chatClient,
  repositoryId,
  historyOpen,
  newChatRequest = 0,
  mentionRequest = EMPTY_MENTION_REQUEST,
  plannerName = null,
  indexClient,
  onOpenWorkspace,
  onOpenModels,
  onApplyFile,
  onOpenPath,
}: ChatPageProps) {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mentionPaths, setMentionPaths] = useState<string[]>([]);
  const [mentionHighlight, setMentionHighlight] = useState(0);
  const [mentionHint, setMentionHint] = useState<"building" | "empty" | null>(null);
  const [composerImages, setComposerImages] = useState<ChatComposerImage[]>([]);
  const inflightSessionId = useRef<string | null>(null);
  const threadRef = useRef<HTMLOListElement | null>(null);
  const composerRef = useRef<HTMLTextAreaElement | null>(null);
  const imageInputRef = useRef<HTMLInputElement | null>(null);

  function closeMentionPicker(): void {
    setMentionPaths([]);
    setMentionHighlight(0);
    setMentionHint(null);
  }

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
    if (mentionRequest.nonce === 0 || mentionRequest.path.trim() === "") {
      return;
    }
    setDraft((current) =>
      appendAskInChatDraft(current, mentionRequest.path, excerptFromMentionRequest(mentionRequest)),
    );
    requestAnimationFrame(() => {
      composerRef.current?.focus();
    });
  }, [mentionRequest]);

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
      closeMentionPicker();
      return;
    }
    const cursor = composerRef.current?.selectionStart ?? draft.length;
    const mention = mentionQueryAtCursor(draft, cursor);
    if (!mention || mention.query === "") {
      closeMentionPicker();
      return;
    }
    let cancelled = false;
    void Promise.all([
      indexClient.status(repositoryId),
      indexClient.search(repositoryId, mention.query),
    ]).then(
      ([status, hits]) => {
        if (cancelled) {
          return;
        }
        const paths = uniqueMentionPaths(hits).slice(0, 8);
        setMentionPaths(paths);
        setMentionHighlight(0);
        if (paths.length > 0) {
          setMentionHint(null);
        } else if (!status.ready) {
          setMentionHint("building");
        } else {
          setMentionHint("empty");
        }
      },
      () => {
        if (!cancelled) {
          closeMentionPicker();
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
    setComposerImages([]);
    setError(null);
    closeMentionPicker();
  }

  async function onSend() {
    await sendText(draft.trim(), { clearDraft: true, images: composerImages });
  }

  async function onRetry() {
    await sendText(lastUserMessageText(messages), { clearDraft: false, images: [] });
  }

  async function sendText(
    text: string,
    options: { clearDraft: boolean; images: ChatComposerImage[] },
  ): Promise<void> {
    if ((text === "" && options.images.length === 0) || busy) {
      return;
    }
    const pending: ChatMessage = {
      id: `local_${Date.now()}`,
      role: "user",
      content: text,
      toolName: null,
      toolStatus: null,
      previewUrls: options.images.map((image) => image.previewUrl),
    };
    setBusy(true);
    setError(null);
    if (options.clearDraft) {
      setDraft("");
      setComposerImages([]);
    }
    closeMentionPicker();
    setMessages((current) => [...current, pending]);
    if (activeId) {
      inflightSessionId.current = activeId;
    }
    try {
      const id = await ensureSession();
      inflightSessionId.current = id;
      const result =
        options.images.length > 0
          ? await chatClient.sendMessage(
              id,
              text,
              repositoryId,
              options.images.map((image) => ({ mime: image.mime, data: image.data })),
            )
          : await chatClient.sendMessage(id, text, repositoryId);
      setMessages(result.messages);
      const listed = await chatClient.listSessions();
      setSessions(listed);
    } catch {
      setMessages((current) => current.filter((item) => item.id !== pending.id));
      if (options.clearDraft) {
        setDraft(text);
        setComposerImages(options.images);
      }
      setError("Could not send that message. Check the model connection and try again.");
    } finally {
      inflightSessionId.current = null;
      setBusy(false);
    }
  }

  async function addImageFiles(files: File[]): Promise<void> {
    if (files.length === 0) {
      setError(pastedImageError("type"));
      return;
    }
    const accepted: ChatComposerImage[] = [];
    let failure: "type" | "size" | null = null;
    for (const file of files) {
      const result = await readPastedImageFile(file);
      if (!result.ok) {
        failure = result.reason;
        continue;
      }
      accepted.push({
        id: `local_${crypto.randomUUID()}`,
        mime: result.mime,
        data: result.data,
        previewUrl: dataUrlForChatImage(result.mime, result.data),
      });
    }
    if (accepted.length === 0) {
      setError(pastedImageError(failure ?? "type"));
      return;
    }
    const room = MAX_CHAT_IMAGES_PER_TURN - composerImages.length;
    if (room <= 0) {
      setError(pastedImageError("limit"));
      return;
    }
    if (accepted.length > room) {
      setError(pastedImageError("limit"));
    } else if (failure) {
      setError(pastedImageError(failure));
    } else {
      setError(null);
    }
    setComposerImages((current) => [...current, ...accepted.slice(0, room)]);
  }

  function removeComposerImage(id: string): void {
    setComposerImages((current) => current.filter((image) => image.id !== id));
  }

  async function onComposerPaste(event: ClipboardEvent<HTMLTextAreaElement>): Promise<void> {
    const data = event.clipboardData;
    if (!clipboardHasFiles(data)) {
      return;
    }
    event.preventDefault();
    closeMentionPicker();
    try {
      await addImageFiles(imageFilesFromClipboard(data));
    } catch {
      setError("Could not read that image. Use Add image instead.");
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
    closeMentionPicker();
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

  useEffect(() => {
    if (!busy) {
      return;
    }
    function onKey(event: KeyboardEvent): void {
      if (event.key !== "Escape") {
        return;
      }
      event.preventDefault();
      void onStop();
    }
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
    };
  }, [busy]);

  const contextUsage = chatContextUsage([...messages.map((item) => item.content), draft]);
  const contextLabel = chatContextMeterLabel(contextUsage);
  const contextWarn = chatContextWarning(contextUsage.ratio);
  const contextPercent = Math.round(contextUsage.ratio * 100);

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
                ? "Chat can search this workspace, read and write files, run commands, and start a longer goal when you want unattended work. AGENTS.md and Cursor rules files in this folder are followed on every turn. Apply on a code block writes that file here. Click a file mention to open it in Files. Paste a screenshot to ask about the UI."
                : "You can ask how Kronos works now. Paste a screenshot, or open a git folder to index code."}
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
                {item.role === "assistant" ? (
                  <ChatMarkdown source={item.content} onApply={onApplyFile} onOpenPath={onOpenPath} />
                ) : item.role === "user" ? (
                  <UserMessage
                    content={item.content}
                    previewUrls={item.previewUrls}
                    sessionId={activeId}
                    chatClient={chatClient}
                    onOpenPath={onOpenPath}
                  />
                ) : item.role === "tool" ? (
                  <>
                    <p className="chat-bubble__tool">{toolCardLabel(item.toolName, item.toolStatus)}</p>
                    {item.toolName === "run_command" ? (
                      <div className="chat-bubble__output-wrap">
                        <CopyTextButton text={item.content} idleLabel="Copy output" />
                        <pre className="chat-bubble__output">{item.content}</pre>
                      </div>
                    ) : (
                      <p>{item.content}</p>
                    )}
                  </>
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
        {error ? (
          <div className="chat-send-error">
            <p className="wizard__error">{error}</p>
            <button type="button" className="btn-quiet" onClick={() => void onSend()}>
              Try again
            </button>
          </div>
        ) : null}
        {!busy && !error && lastUserMessageText(messages) !== "" ? (
          <div className="chat-retry">
            <button type="button" className="btn-quiet" onClick={() => void onRetry()}>
              Retry
            </button>
          </div>
        ) : null}
        <div
          className="chat-composer-wrap"
          onDragOver={(event: DragEvent<HTMLDivElement>) => {
            event.preventDefault();
          }}
          onDrop={(event: DragEvent<HTMLDivElement>) => {
            if (!clipboardHasFiles(event.dataTransfer)) {
              return;
            }
            event.preventDefault();
            void addImageFiles(imageFilesFromClipboard(event.dataTransfer));
          }}
        >
          {mentionHint ? (
            <p className="chat-mentions chat-mentions--hint" role="status">
              {mentionHint === "building"
                ? "The search index is still building."
                : "No matching files."}
            </p>
          ) : null}
          {mentionPaths.length > 0 ? (
            <ul className="chat-mentions" id="chat-mentions" role="listbox" aria-label="Workspace files">
              {mentionPaths.map((path, index) => (
                <li key={path} role="presentation">
                  <button
                    type="button"
                    id={`chat-mention-${index}`}
                    className="chat-mentions__item"
                    role="option"
                    aria-selected={index === mentionHighlight}
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
          <input
            ref={imageInputRef}
            type="file"
            accept="image/png,image/jpeg,image/webp,image/gif"
            multiple
            className="visually-hidden"
            aria-label="Add image"
            onChange={(event) => {
              const files = [...(event.target.files ?? [])];
              event.target.value = "";
              if (files.length > 0) {
                void addImageFiles(files);
              }
            }}
          />
          <label className="chat-composer">
            <span className="visually-hidden">Ask Kronos</span>
            {composerImages.length > 0 ? (
              <ul className="chat-composer__images" aria-label="Pasted images">
                {composerImages.map((image) => (
                  <li key={image.id} className="chat-composer__image">
                    <img src={image.previewUrl} alt="Pasted image" />
                    <button
                      type="button"
                      className="btn-quiet"
                      aria-label="Remove pasted image"
                      onClick={() => {
                        removeComposerImage(image.id);
                      }}
                    >
                      Remove
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
            <textarea
              ref={composerRef}
              className="chat-composer__input"
              value={draft}
              placeholder={
                repositoryId
                  ? "Ask Kronos. Paste a screenshot, or type @ to mention a file."
                  : "Ask Kronos. Paste a screenshot."
              }
              aria-label="Ask Kronos"
              aria-autocomplete="list"
              aria-expanded={mentionPaths.length > 0}
              aria-controls={mentionPaths.length > 0 ? "chat-mentions" : undefined}
              aria-activedescendant={
                mentionPaths.length > 0 ? `chat-mention-${mentionHighlight}` : undefined
              }
              rows={2}
              onChange={(event) => {
                setDraft(event.target.value);
                const node = event.target;
                node.style.height = "auto";
                node.style.height = `${Math.min(200, Math.max(44, node.scrollHeight))}px`;
              }}
              onPaste={(event) => {
                void onComposerPaste(event);
              }}
              onKeyDown={(event) => {
                if (event.key === "Escape" && (mentionPaths.length > 0 || mentionHint)) {
                  event.preventDefault();
                  closeMentionPicker();
                  return;
                }
                if (event.key === "ArrowDown" && mentionPaths.length > 0) {
                  event.preventDefault();
                  setMentionHighlight((current) => Math.min(mentionPaths.length - 1, current + 1));
                  return;
                }
                if (event.key === "ArrowUp" && mentionPaths.length > 0) {
                  event.preventDefault();
                  setMentionHighlight((current) => Math.max(0, current - 1));
                  return;
                }
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  const chosen = mentionPaths[mentionHighlight] ?? mentionPaths[0];
                  if (chosen) {
                    applyMention(chosen);
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
              <span
                className="chat-context"
                data-context-full={contextUsage.ratio >= 0.8 ? "true" : undefined}
              >
                <span
                  className="chat-context__bar"
                  role="progressbar"
                  aria-label={contextLabel}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={contextPercent}
                >
                  <span className="chat-context__fill" style={{ width: `${contextPercent}%` }} />
                </span>
                <span className="chat-context__label">{contextLabel}</span>
              </span>
              <button
                type="button"
                className="btn-quiet"
                onClick={() => {
                  imageInputRef.current?.click();
                }}
              >
                Add image
              </button>
              <button
                type="button"
                className={busy ? "btn-quiet" : "btn-primary"}
                disabled={busy || (draft.trim() === "" && composerImages.length === 0)}
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
            {contextWarn ? (
              <p className="chat-context__warn" role="status">
                {contextWarn}
              </p>
            ) : null}
          </label>
        </div>
      </section>
    </div>
  );
}

function UserMessage({
  content,
  previewUrls,
  sessionId,
  chatClient,
  onOpenPath,
}: {
  content: string;
  previewUrls: string[] | undefined;
  sessionId: string | null;
  chatClient: ChatClient;
  onOpenPath: ((path: string) => void) | undefined;
}) {
  if (previewUrls && previewUrls.length > 0) {
    return (
      <>
        {content.trim() !== "" ? <UserMentionText content={content} onOpenPath={onOpenPath} /> : null}
        {previewUrls.map((url) => (
          <img key={url} className="chat-bubble__image" alt="Pasted image" src={url} />
        ))}
      </>
    );
  }
  const segments = userMessageSegments(content);
  return (
    <>
      {segments.map((part, index) => {
        if (part.kind === "image" && sessionId) {
          return (
            <ChatPastedImage
              key={`${part.value}:${index}`}
              sessionId={sessionId}
              imageId={part.value}
              chatClient={chatClient}
            />
          );
        }
        if (part.kind === "image") {
          return (
            <span key={`${part.value}:${index}`} className="chat-bubble__image-fallback">
              Pasted image
            </span>
          );
        }
        return <UserMentionText key={`${part.value}:${index}`} content={part.value} onOpenPath={onOpenPath} />;
      })}
    </>
  );
}

function ChatPastedImage({
  sessionId,
  imageId,
  chatClient,
}: {
  sessionId: string;
  imageId: string;
  chatClient: ChatClient;
}) {
  const [src, setSrc] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    void chatClient.getImage(sessionId, imageId).then(
      (payload) => {
        if (!cancelled) {
          setSrc(dataUrlForChatImage(payload.mime, payload.data));
        }
      },
      () => undefined,
    );
    return () => {
      cancelled = true;
    };
  }, [chatClient, imageId, sessionId]);
  if (!src) {
    return <span className="chat-bubble__image-fallback">Pasted image</span>;
  }
  return <img className="chat-bubble__image" alt="Pasted image" src={src} />;
}

function UserMentionText({
  content,
  onOpenPath,
}: {
  content: string;
  onOpenPath: ((path: string) => void) | undefined;
}) {
  return (
    <p>
      {mentionSegments(content).map((part, index) => {
        if (part.kind !== "path") {
          return <span key={`${part.value}:${index}`}>{part.value}</span>;
        }
        const path = safeWorkspaceRelPath(part.value);
        if (onOpenPath && path !== "") {
          return <ChatPathButton key={`${part.value}:${index}`} path={path} onOpen={onOpenPath} />;
        }
        return <code key={`${part.value}:${index}`}>{part.value}</code>;
      })}
    </p>
  );
}

function lastUserMessageText(messages: ChatMessage[]): string {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const item = messages[index];
    if (item?.role === "user") {
      return item.content.trim();
    }
  }
  return "";
}
