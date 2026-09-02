// SPDX-License-Identifier: AGPL-3.0-or-later

import { useEffect, useRef, useState, type ClipboardEvent, type DragEvent } from "react";
import { ConnectModelGate } from "../../shell/ConnectModelGate";
import { safeWorkspaceRelPath } from "../files/workspacePath";
import type { IndexClient } from "../index/client";
import type { ModelsClient, ModelProfileOption, RoleAssignments } from "../models/client";
import { DEFAULT_CONTEXT_WINDOW } from "../models/client";
import { ChatMarkdown } from "./ChatMarkdown";
import { ChatPathButton } from "./ChatPathButton";
import {
  chatContextMeterLabel,
  chatContextUsage,
  chatContextWarning,
} from "./contextMeter";
import { CopyTextButton } from "./CopyTextButton";
import type {
  ChatClient,
  ChatGoalEvent,
  ChatMessage,
  ChatToolEvent,
  ConversationSummary,
} from "./client";
import {
  appendAskInChatDraft,
  excerptFromMentionRequest,
  insertMention,
  mentionQueryAtCursor,
  mentionSegments,
  uniqueMentionPaths,
} from "./mentionQuery";
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
import { toolCardLabel, toolDisplayName } from "./toolCard";
import { streamStatusMessage, STREAM_STATUS_SETTLE_MS, type StreamPhase } from "./streamStatus";

const EMPTY_MENTION_REQUEST = { path: "", nonce: 0, selectedText: "", startLine: 0, endLine: 0 };

export interface ChatMentionRequest {
  path: string;
  nonce: number;
  selectedText?: string;
  startLine?: number;
  endLine?: number;
}

interface ThreadItem extends ChatMessage {
  goalEvent?: ChatGoalEvent;
  streaming?: boolean;
}

interface ChatPageProps {
  chatClient: ChatClient;
  repositoryId: string | null;
  historyOpen: boolean;
  newChatRequest?: number;
  mentionRequest?: ChatMentionRequest;
  orchestratorName?: string | null;
  indexClient?: IndexClient;
  modelsClient?: ModelsClient;
  onOpenWorkspace: () => void;
  onOpenModels?: () => void;
  onOpenGoals?: () => void;
  onApplyFile?: ((path: string, content: string) => Promise<void>) | undefined;
  onOpenPath?: ((path: string) => void) | undefined;
}

export function ChatPage({
  chatClient,
  repositoryId,
  historyOpen,
  newChatRequest = 0,
  mentionRequest = EMPTY_MENTION_REQUEST,
  orchestratorName = null,
  indexClient,
  modelsClient,
  onOpenWorkspace,
  onOpenModels,
  onOpenGoals,
  onApplyFile,
  onOpenPath,
}: ChatPageProps) {
  const [sessions, setSessions] = useState<ConversationSummary[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ThreadItem[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [streamPhase, setStreamPhase] = useState<StreamPhase>("idle");
  const [activeToolLabel, setActiveToolLabel] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mentionPaths, setMentionPaths] = useState<string[]>([]);
  const [mentionHighlight, setMentionHighlight] = useState(0);
  const [mentionHint, setMentionHint] = useState<"building" | "empty" | null>(null);
  const [composerImages, setComposerImages] = useState<ChatComposerImage[]>([]);
  const [modelMenuOpen, setModelMenuOpen] = useState(false);
  const [connectOpen, setConnectOpen] = useState(false);
  const [profiles, setProfiles] = useState<ModelProfileOption[]>([]);
  const [assignments, setAssignments] = useState<RoleAssignments | null>(null);
  const [contextWindow, setContextWindow] = useState(DEFAULT_CONTEXT_WINDOW);
  const [modelLabel, setModelLabel] = useState<string | null>(orchestratorName);
  const inflightRef = useRef<{ conversationId: string; requestId: string } | null>(null);
  const threadRef = useRef<HTMLOListElement | null>(null);
  const composerRef = useRef<HTMLTextAreaElement | null>(null);
  const imageInputRef = useRef<HTMLInputElement | null>(null);
  const skipSelectRef = useRef(false);
  const streamIdleTimerRef = useRef<number | null>(null);
  const turnEpochRef = useRef(0);

  function clearStreamIdleTimer(): void {
    if (streamIdleTimerRef.current !== null) {
      window.clearTimeout(streamIdleTimerRef.current);
      streamIdleTimerRef.current = null;
    }
  }

  function resetStreamStatus(): void {
    clearStreamIdleTimer();
    setStreamPhase("idle");
    setActiveToolLabel(null);
  }

  function settleStreamStatus(phase: Extract<StreamPhase, "done" | "error">): void {
    clearStreamIdleTimer();
    setStreamPhase(phase);
    setActiveToolLabel(null);
    streamIdleTimerRef.current = window.setTimeout(() => {
      streamIdleTimerRef.current = null;
      setStreamPhase("idle");
    }, STREAM_STATUS_SETTLE_MS);
  }

  function abandonInflightTurn(): void {
    turnEpochRef.current += 1;
    const abandoned = inflightRef.current;
    inflightRef.current = null;
    setBusy(false);
    resetStreamStatus();
    if (!abandoned) {
      return;
    }
    void chatClient.cancelStream(abandoned.conversationId, abandoned.requestId).catch(() => undefined);
  }

  function closeMentionPicker(): void {
    setMentionPaths([]);
    setMentionHighlight(0);
    setMentionHint(null);
  }

  useEffect(() => {
    setModelLabel(orchestratorName);
  }, [orchestratorName]);

  useEffect(() => {
    if (!modelsClient) {
      return;
    }
    let cancelled = false;
    void modelsClient.snapshot().then(
      (snapshot) => {
        if (cancelled) {
          return;
        }
        applySnapshot(snapshot.profiles, snapshot.assignments);
      },
      () => undefined,
    );
    return () => {
      cancelled = true;
    };
  }, [modelsClient]);

  function applySnapshot(nextProfiles: ModelProfileOption[], nextAssignments: RoleAssignments): void {
    setProfiles(nextProfiles);
    setAssignments(nextAssignments);
    const orch = nextProfiles.find((item) => item.id === nextAssignments.orchestrator);
    if (orch) {
      setModelLabel(orch.displayName);
      setContextWindow(orch.limits.contextWindow || DEFAULT_CONTEXT_WINDOW);
    } else {
      setContextWindow(DEFAULT_CONTEXT_WINDOW);
    }
  }

  useEffect(() => {
    let cancelled = false;
    void Promise.all([
      repositoryId ? chatClient.listConversations(repositoryId) : Promise.resolve([]),
      chatClient.listConversations(null),
    ]).then(async ([scoped, loose]) => {
      if (cancelled) {
        return;
      }
      const items = mergeHistory(scoped, loose, repositoryId);
      setSessions(items);
      const first = items[0];
      if (!first || skipSelectRef.current) {
        return;
      }
      setActiveId(first.id);
      const payload = await chatClient.getConversation(first.id);
      if (!cancelled) {
        setMessages(payload.messages);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [chatClient, repositoryId]);

  useEffect(() => {
    if (newChatRequest === 0) {
      return;
    }
    skipSelectRef.current = true;
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
    return () => {
      clearStreamIdleTimer();
    };
  }, []);

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

  async function ensureSession(epoch: number): Promise<string | null> {
    if (activeId) {
      return activeId;
    }
    const created = await chatClient.createConversation(repositoryId);
    if (turnEpochRef.current !== epoch) {
      return null;
    }
    setSessions((current) => [created, ...current.filter((item) => item.id !== created.id)]);
    setActiveId(created.id);
    return created.id;
  }

  async function startNewChat(): Promise<void> {
    abandonInflightTurn();
    setActiveId(null);
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
    const requestId = crypto.randomUUID();
    const pending: ThreadItem = {
      id: `local_user_${requestId}`,
      role: "user",
      content: text,
      citations: [],
      goalRefs: [],
      toolName: null,
      toolStatus: null,
      toolJson: null,
      previewUrls: options.images.map((image) => image.previewUrl),
    };
    const assistantId = `local_asst_${requestId}`;
    const assistant: ThreadItem = {
      id: assistantId,
      role: "assistant",
      content: "",
      citations: [],
      goalRefs: [],
      toolName: null,
      toolStatus: null,
      toolJson: null,
      streaming: true,
    };
    setError(null);
    clearStreamIdleTimer();
    setStreamPhase("streaming");
    setActiveToolLabel(null);
    if (options.clearDraft) {
      setDraft("");
      setComposerImages([]);
    }
    closeMentionPicker();
    setMessages((current) => [...current, pending, assistant]);
    const epoch = turnEpochRef.current;
    try {
      const id = await ensureSession(epoch);
      if (id === null || turnEpochRef.current !== epoch) {
        return;
      }
      inflightRef.current = { conversationId: id, requestId };
      setBusy(true);
      let failed = false;
      const stillThisTurn = () => turnEpochRef.current === epoch;
      await chatClient.streamMessage(id, text, {
        requestId,
        images: options.images.map((image) => ({ mime: image.mime, data: image.data })),
        onDelta: (delta) => {
          if (!stillThisTurn()) {
            return;
          }
          setMessages((current) =>
            current.map((item) =>
              item.id === assistantId ? { ...item, content: item.content + delta } : item,
            ),
          );
        },
        onTool: (tool) => {
          if (!stillThisTurn()) {
            return;
          }
          if (tool.status === "running") {
            setStreamPhase("tool");
            setActiveToolLabel(toolDisplayName(tool.name));
          } else {
            setStreamPhase("streaming");
            setActiveToolLabel(null);
          }
          setMessages((current) => upsertToolMessage(current, tool, assistantId));
        },
        onGoal: (goal) => {
          if (!stillThisTurn()) {
            return;
          }
          setMessages((current) => upsertGoalMessage(current, goal, assistantId));
        },
        onDone: (result) => {
          if (!stillThisTurn()) {
            return;
          }
          settleStreamStatus("done");
          setMessages((current) =>
            current.map((item) =>
              item.id === assistantId
                ? {
                    ...item,
                    content: result.content || item.content,
                    citations: result.citations,
                    goalRefs: result.goalRefs,
                    streaming: false,
                  }
                : item,
            ),
          );
        },
        onError: () => {
          if (!stillThisTurn()) {
            return;
          }
          failed = true;
          settleStreamStatus("error");
        },
      });
      if (!stillThisTurn()) {
        return;
      }
      if (failed) {
        setMessages((current) => current.filter((item) => item.id !== pending.id && item.id !== assistantId));
        if (options.clearDraft) {
          setDraft(text);
          setComposerImages(options.images);
        }
        setError("Could not send that message. Check the model connection and try again.");
        settleStreamStatus("error");
      }
    } catch {
      if (turnEpochRef.current !== epoch) {
        return;
      }
      setMessages((current) => current.filter((item) => item.id !== pending.id && item.id !== assistantId));
      if (options.clearDraft) {
        setDraft(text);
        setComposerImages(options.images);
      }
      setError("Could not send that message. Check the model connection and try again.");
      settleStreamStatus("error");
    } finally {
      if (turnEpochRef.current === epoch) {
        inflightRef.current = null;
        setBusy(false);
      }
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
    const inflight = inflightRef.current;
    if (!inflight) {
      setBusy(false);
      return;
    }
    try {
      await chatClient.cancelStream(inflight.conversationId, inflight.requestId);
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

  async function onSelectProfile(profileId: string): Promise<void> {
    if (!modelsClient || !assignments) {
      setModelMenuOpen(false);
      return;
    }
    setModelMenuOpen(false);
    const planner = assignments.planner;
    const coder = assignments.coder;
    const reviewer = assignments.reviewer;
    const embedding = assignments.embedding;
    if (!planner || !coder || !reviewer || !embedding) {
      setError("Could not switch the orchestrator model. Try again.");
      return;
    }
    const selected = profiles.find((item) => item.id === profileId);
    const payload = {
      orchestrator: profileId,
      planner,
      coder,
      reviewer,
      embedding,
    };
    try {
      const saved =
        selected && selected.role !== "orchestrator"
          ? await modelsClient.assign(payload, { confirmSharedRoles: true })
          : await modelsClient.assign(payload);
      applySnapshot(profiles, saved);
    } catch {
      setError("Could not switch the orchestrator model. Try again.");
    }
  }

  const contextUsage = chatContextUsage(
    [...messages.map((item) => item.content), draft],
    contextWindow,
  );
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
                    abandonInflightTurn();
                    setActiveId(item.id);
                    void chatClient.getConversation(item.id).then((payload) => {
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
                ? "Ask about this workspace, paste a screenshot, or type /goal for unattended work."
                : "Ask how Kronos works, or open a git folder to index code."}
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
                className={`chat-bubble chat-bubble--${item.role}${item.streaming ? " chat-bubble--streaming" : ""}${item.role === "tool" && item.toolStatus ? ` chat-bubble--tool-${item.toolStatus}` : ""}`}
                data-tool={item.toolName ?? undefined}
              >
                {item.goalEvent ? (
                  <GoalCard goal={item.goalEvent} onOpenGoals={onOpenGoals} />
                ) : item.role === "assistant" ? (
                  <>
                    {item.content.trim() !== "" || item.streaming ? (
                      <ChatMarkdown source={item.content} onApply={onApplyFile} onOpenPath={onOpenPath} />
                    ) : null}
                    {item.citations.length > 0 ? (
                      <ul className="chat-citations">
                        {item.citations.map((citation) => (
                          <li key={`${citation.path}:${citation.startLine}`}>
                            <span className="chat-citations__chip">
                              {citation.path}:{citation.startLine}
                            </span>
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </>
                ) : item.role === "user" ? (
                  <UserMessage
                    content={item.content}
                    previewUrls={item.previewUrls}
                    conversationId={activeId}
                    chatClient={chatClient}
                    onOpenPath={onOpenPath}
                  />
                ) : item.role === "tool" ? (
                  <ToolCard message={item} />
                ) : (
                  <p>{item.content}</p>
                )}
              </li>
            ))}
          </ol>
        )}
        {streamStatusMessage(streamPhase, activeToolLabel ?? undefined) ? (
          <p className="chat-turn-status" role="status" aria-live="polite">
            {streamStatusMessage(streamPhase, activeToolLabel ?? undefined)}
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
              {modelLabel ? (
                <span className="chat-composer__model-wrap">
                  <button
                    type="button"
                    className="chat-composer__model"
                    aria-haspopup={modelsClient ? "menu" : undefined}
                    aria-expanded={modelsClient ? modelMenuOpen : undefined}
                    onClick={() => {
                      if (modelsClient) {
                        setModelMenuOpen((open) => !open);
                        return;
                      }
                      onOpenModels?.();
                    }}
                  >
                    {modelLabel}
                  </button>
                  {modelsClient && modelMenuOpen ? (
                    <ul className="chat-model-menu" role="menu" aria-label="Orchestrator models">
                      {profiles.map((profile) => (
                        <li key={profile.id} role="none">
                          <button
                            type="button"
                            role="menuitem"
                            className="chat-model-menu__item"
                            onClick={() => {
                              void onSelectProfile(profile.id);
                            }}
                          >
                            {profile.displayName}
                          </button>
                        </li>
                      ))}
                      <li role="none">
                        <button
                          type="button"
                          role="menuitem"
                          className="chat-model-menu__item"
                          onClick={() => {
                            setModelMenuOpen(false);
                            setConnectOpen(true);
                          }}
                        >
                          Connect a model…
                        </button>
                      </li>
                    </ul>
                  ) : null}
                </span>
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
      {connectOpen && modelsClient ? (
        <div
          className="chat-model-dialog-backdrop"
          role="presentation"
          onClick={() => {
            setConnectOpen(false);
          }}
        >
          <div
            className="chat-model-dialog"
            role="dialog"
            aria-modal="true"
            aria-label="Connect a model"
            onClick={(event) => {
              event.stopPropagation();
            }}
          >
            <ConnectModelGate
              modelsClient={modelsClient}
              onConnected={() => {
                setConnectOpen(false);
                void modelsClient.snapshot().then((snapshot) => {
                  applySnapshot(snapshot.profiles, snapshot.assignments);
                });
              }}
            />
            <button
              type="button"
              className="btn-quiet"
              onClick={() => {
                setConnectOpen(false);
              }}
            >
              Close
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function mergeHistory(
  scoped: ConversationSummary[],
  loose: ConversationSummary[],
  repositoryId: string | null,
): ConversationSummary[] {
  const seen = new Set<string>();
  const items: ConversationSummary[] = [];
  for (const item of [...scoped, ...loose]) {
    if (seen.has(item.id)) {
      continue;
    }
    if (item.repositoryId !== null && item.repositoryId !== repositoryId) {
      continue;
    }
    seen.add(item.id);
    items.push(item);
  }
  return items;
}

function upsertToolMessage(
  current: ThreadItem[],
  tool: ChatToolEvent,
  assistantId: string,
): ThreadItem[] {
  const id = `tool-${tool.id}`;
  const next: ThreadItem = {
    id,
    role: "tool",
    content: tool.summary ?? "",
    citations: [],
    goalRefs: [],
    toolName: tool.name,
    toolStatus: tool.status,
    toolJson: JSON.stringify({
      args: tool.args ?? {},
      summary: tool.summary ?? "",
      output: tool.output ?? "",
    }),
  };
  const existing = current.findIndex((item) => item.id === id);
  if (existing >= 0) {
    return current.map((item, index) => (index === existing ? next : item));
  }
  const assistantIndex = current.findIndex((item) => item.id === assistantId);
  if (assistantIndex < 0) {
    return [...current, next];
  }
  return [...current.slice(0, assistantIndex), next, ...current.slice(assistantIndex)];
}

function upsertGoalMessage(
  current: ThreadItem[],
  goal: ChatGoalEvent,
  assistantId: string,
): ThreadItem[] {
  const id = `goal-${goal.id}`;
  const next: ThreadItem = {
    id,
    role: "assistant",
    content: "",
    citations: [],
    goalRefs: [goal.id],
    toolName: null,
    toolStatus: null,
    toolJson: null,
    goalEvent: goal,
  };
  const existing = current.findIndex((item) => item.id === id);
  if (existing >= 0) {
    return current.map((item, index) => (index === existing ? next : item));
  }
  const assistantIndex = current.findIndex((item) => item.id === assistantId);
  if (assistantIndex < 0) {
    return [...current, next];
  }
  return [...current.slice(0, assistantIndex), next, ...current.slice(assistantIndex)];
}

function ToolCard({ message }: { message: ThreadItem }) {
  const parsed = parseToolJson(message.toolJson);
  const summary = parsed.summary || message.content;
  const output = parsed.output || (message.toolName === "run_command" ? message.content : "");
  return (
    <>
      <p className="chat-bubble__tool">{toolCardLabel(message.toolName, message.toolStatus)}</p>
      {summary && summary !== output ? <p>{summary}</p> : null}
      {output ? (
        message.toolName === "run_command" ? (
          <div className="chat-bubble__output-wrap">
            <CopyTextButton text={output} idleLabel="Copy output" />
            <pre className="chat-bubble__output">{output}</pre>
          </div>
        ) : (
          <details className="chat-bubble__details" open={message.toolStatus === "ok"}>
            <summary>Output</summary>
            <div className="chat-bubble__output-wrap">
              <CopyTextButton text={output} idleLabel="Copy output" />
              <pre className="chat-bubble__output">{output}</pre>
            </div>
          </details>
        )
      ) : null}
    </>
  );
}

function GoalCard({
  goal,
  onOpenGoals,
}: {
  goal: ChatGoalEvent;
  onOpenGoals: (() => void) | undefined;
}) {
  return (
    <article className="chat-goal-card">
      <p className="chat-goal-card__id">{goal.id}</p>
      <p className="chat-goal-card__state">{goal.state}</p>
      <ul className="chat-goal-card__checks">
        {goal.readiness.map((check) => (
          <li key={check.id}>
            {check.label}: {check.ok ? "ready." : check.detail}
          </li>
        ))}
      </ul>
      {onOpenGoals ? (
        <button type="button" className="btn-quiet" onClick={onOpenGoals}>
          Open in Goals
        </button>
      ) : null}
    </article>
  );
}

function parseToolJson(raw: string | null): { summary: string; output: string } {
  if (!raw) {
    return { summary: "", output: "" };
  }
  try {
    const parsed = JSON.parse(raw) as { summary?: unknown; output?: unknown };
    return {
      summary: typeof parsed.summary === "string" ? parsed.summary : "",
      output: typeof parsed.output === "string" ? parsed.output : "",
    };
  } catch {
    return { summary: "", output: "" };
  }
}

function UserMessage({
  content,
  previewUrls,
  conversationId,
  chatClient,
  onOpenPath,
}: {
  content: string;
  previewUrls: string[] | undefined;
  conversationId: string | null;
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
        if (part.kind === "image" && conversationId) {
          return (
            <ChatPastedImage
              key={`${part.value}:${index}`}
              conversationId={conversationId}
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
  conversationId,
  imageId,
  chatClient,
}: {
  conversationId: string;
  imageId: string;
  chatClient: ChatClient;
}) {
  const [src, setSrc] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    void chatClient.getImage(conversationId, imageId).then(
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
  }, [chatClient, imageId, conversationId]);
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
