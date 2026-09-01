// SPDX-License-Identifier: AGPL-3.0-or-later

import { useEffect, useRef, useState } from "react";
import type { EngineClient } from "../../engine/client";
import {
  createProductionRepositoriesClient,
  type RepositoriesClient,
  type WorkspaceTerminalRun,
} from "../workspaces/client";

const productionRepos = createProductionRepositoriesClient();

interface TerminalPageProps {
  engineClient: EngineClient;
  repositoryId: string | null;
  repositoriesClient?: RepositoriesClient;
  onOpenWorkspace: () => void;
}

export function TerminalPage({
  engineClient,
  repositoryId,
  repositoriesClient,
  onOpenWorkspace,
}: TerminalPageProps) {
  const client = repositoriesClient ?? productionRepos;
  const [ready, setReady] = useState(false);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [run, setRun] = useState<WorkspaceTerminalRun | null>(null);
  const [history, setHistory] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState<number | null>(null);
  const [historyStash, setHistoryStash] = useState("");
  const stoppingRef = useRef(false);
  const outputRef = useRef<HTMLPreElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const runRef = useRef<WorkspaceTerminalRun | null>(null);
  const previousRepoRef = useRef<string | null>(null);
  runRef.current = run;

  useEffect(() => {
    const previous = previousRepoRef.current;
    if (previous !== null && previous !== repositoryId) {
      void client.cancelWorkspaceCommand(previous);
      setRun(null);
    }
    previousRepoRef.current = repositoryId;
  }, [client, repositoryId]);

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
    if (!ready || !repositoryId) {
      return;
    }
    let cancelled = false;
    setError(null);
    void client.startWorkspaceShell(repositoryId).then(
      (snapshot) => {
        if (!cancelled) {
          setRun(snapshot);
        }
      },
      () => {
        if (!cancelled) {
          setError("Could not start the workspace shell. Check that the engine is running, then try again.");
        }
      },
    );
    return () => {
      cancelled = true;
    };
  }, [client, ready, repositoryId]);

  async function ensureShell(): Promise<boolean> {
    if (!repositoryId) {
      return false;
    }
    if (runRef.current?.running === true) {
      return true;
    }
    try {
      const snapshot = await client.startWorkspaceShell(repositoryId);
      setRun(snapshot);
      runRef.current = snapshot;
      return snapshot.running === true;
    } catch {
      setError("Could not start the workspace shell. Check that the engine is running, then try again.");
      return false;
    }
  }

  async function onSend(): Promise<void> {
    const line = draft.trim();
    if (line === "" || sending || !repositoryId) {
      return;
    }
    setSending(true);
    setError(null);
    setHistory((current) => rememberCommand(current, line));
    setHistoryIndex(null);
    setHistoryStash("");
    try {
      const live = await ensureShell();
      if (!live) {
        return;
      }
      await client.writeWorkspaceShell(repositoryId, line);
      setDraft("");
      inputRef.current?.focus();
    } catch {
      setError("Could not send that line. Check that the engine is running, then try again.");
    } finally {
      setSending(false);
    }
  }

  async function onStop(): Promise<void> {
    if (!repositoryId || stoppingRef.current || runRef.current?.running !== true) {
      return;
    }
    stoppingRef.current = true;
    try {
      await client.cancelWorkspaceCommand(repositoryId);
      setRun((current) =>
        current === null ? current : { ...current, running: false, cancelled: true },
      );
    } catch {
      setError("Could not stop that command. Wait for it to finish, then try again.");
    } finally {
      stoppingRef.current = false;
    }
  }

  useEffect(() => {
    if (!ready || !repositoryId) {
      return;
    }
    let cancelled = false;
    const pull = () => {
      void client.watchWorkspaceCommand(repositoryId).then((snapshot) => {
        if (cancelled) {
          return;
        }
        setRun((current) => mergeTerminalSnapshot(current, snapshot));
      }, () => undefined);
    };
    pull();
    const timer = window.setInterval(pull, 150);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [ready, client, repositoryId]);

  useEffect(() => {
    const node = outputRef.current;
    if (node) {
      node.scrollTop = node.scrollHeight;
    }
  }, [run?.output]);

  if (!ready) {
    return (
      <section className="terminal-page">
        <h2 className="terminal-page__title">Terminal</h2>
        <p className="terminal-page__status">
          The local engine is not connected. Terminal stays closed until it is.
        </p>
      </section>
    );
  }

  if (!repositoryId) {
    return (
      <section className="terminal-page">
        <h2 className="terminal-page__title">Terminal</h2>
        <p className="terminal-page__status">
          Open a git folder to run commands in that workspace.
        </p>
        <button type="button" className="btn-quiet" onClick={onOpenWorkspace}>
          Open folder
        </button>
      </section>
    );
  }

  const status = runStatus(run);
  const shellOpen = run?.running === true;

  return (
    <section className="terminal-page">
      <header className="terminal-page__head">
        <h2 className="terminal-page__title">Terminal</h2>
        {status ? (
          <p className="terminal-page__status" aria-live="polite">
            {status}
          </p>
        ) : null}
      </header>
      {error ? <p className="wizard__error">{error}</p> : null}
      <div className="terminal-page__form">
        <label className="terminal-page__field">
          <span className="visually-hidden">Command</span>
          <input
            ref={inputRef}
            className="terminal-page__input"
            value={draft}
            aria-label="Command"
            placeholder="npm test"
            disabled={sending}
            spellCheck={false}
            onChange={(event) => {
              setDraft(event.target.value);
            }}
            onKeyDown={(event) => {
              if (event.key === "ArrowUp") {
                event.preventDefault();
                const older = recallOlderCommand(history, historyIndex, draft, historyStash);
                setDraft(older.draft);
                setHistoryIndex(older.index);
                setHistoryStash(older.stash);
                return;
              }
              if (event.key === "ArrowDown") {
                event.preventDefault();
                const newer = recallNewerCommand(history, historyIndex, draft, historyStash);
                setDraft(newer.draft);
                setHistoryIndex(newer.index);
                setHistoryStash(newer.stash);
                return;
              }
              if (event.key === "Escape") {
                event.preventDefault();
                void onStop();
                return;
              }
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void onSend();
              }
            }}
          />
        </label>
        <button
          type="button"
          className="btn-primary"
          disabled={sending || draft.trim() === ""}
          onClick={() => {
            void onSend();
          }}
        >
          Send
        </button>
        {shellOpen ? (
          <button type="button" className="btn-quiet" onClick={() => void onStop()}>
            Stop
          </button>
        ) : null}
      </div>
      <pre
        ref={outputRef}
        className="terminal-page__output"
        data-empty={run && run.output !== "" ? undefined : "true"}
      >
        {run?.output !== undefined && run.output !== ""
          ? run.output
          : "Type a command in this workspace."}
      </pre>
    </section>
  );
}

function mergeTerminalSnapshot(
  current: WorkspaceTerminalRun | null,
  snapshot: WorkspaceTerminalRun,
): WorkspaceTerminalRun {
  if (snapshot.running === true || snapshot.output !== "") {
    return snapshot;
  }
  if (current !== null && current.output !== "") {
    return { ...current, running: false };
  }
  return snapshot;
}

function runStatus(run: WorkspaceTerminalRun | null): string | null {
  if (run?.running === true) {
    return "Shell is open.";
  }
  if (run?.cancelled) {
    return "Stopped.";
  }
  return null;
}

const MAX_TERMINAL_HISTORY = 50;

function rememberCommand(history: string[], command: string): string[] {
  if (history[history.length - 1] === command) {
    return history;
  }
  const next = [...history, command];
  if (next.length <= MAX_TERMINAL_HISTORY) {
    return next;
  }
  return next.slice(next.length - MAX_TERMINAL_HISTORY);
}

interface HistoryRecall {
  draft: string;
  index: number | null;
  stash: string;
}

function recallOlderCommand(
  history: string[],
  index: number | null,
  draft: string,
  stash: string,
): HistoryRecall {
  if (history.length === 0) {
    return { draft, index, stash };
  }
  if (index === null) {
    return { draft: history[history.length - 1] ?? draft, index: history.length - 1, stash: draft };
  }
  if (index <= 0) {
    return { draft: history[0] ?? draft, index: 0, stash };
  }
  const next = index - 1;
  return { draft: history[next] ?? draft, index: next, stash };
}

function recallNewerCommand(
  history: string[],
  index: number | null,
  draft: string,
  stash: string,
): HistoryRecall {
  if (index === null) {
    return { draft, index, stash };
  }
  if (index >= history.length - 1) {
    return { draft: stash, index: null, stash: "" };
  }
  const next = index + 1;
  return { draft: history[next] ?? draft, index: next, stash };
}
