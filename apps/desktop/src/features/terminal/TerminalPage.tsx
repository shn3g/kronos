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
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [run, setRun] = useState<WorkspaceTerminalRun | null>(null);
  const [history, setHistory] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState<number | null>(null);
  const [historyStash, setHistoryStash] = useState("");
  const stoppingRef = useRef(false);
  const outputRef = useRef<HTMLPreElement | null>(null);

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

  async function onRun(): Promise<void> {
    const command = draft.trim();
    if (command === "" || busy || !repositoryId) {
      return;
    }
    setBusy(true);
    setError(null);
    setHistory((current) => rememberCommand(current, command));
    setHistoryIndex(null);
    setHistoryStash("");
    setRun({
      command,
      exitCode: null,
      timedOut: false,
      cancelled: false,
      running: true,
      output: "",
    });
    try {
      const next = await client.runWorkspaceCommand(repositoryId, command);
      setRun(next);
    } catch {
      setRun(null);
      setError("Could not run that command. Check the workspace and try again.");
    } finally {
      setBusy(false);
    }
  }

  async function onStop(): Promise<void> {
    if (!repositoryId || stoppingRef.current || !busy) {
      return;
    }
    stoppingRef.current = true;
    try {
      await client.cancelWorkspaceCommand(repositoryId);
    } catch {
      setError("Could not stop that command. Wait for it to finish, then try again.");
    } finally {
      stoppingRef.current = false;
    }
  }

  useEffect(() => {
    if (!busy) {
      return;
    }
    function onKey(event: KeyboardEvent): void {
      if (event.key === "Escape") {
        event.preventDefault();
        void onStop();
        return;
      }
      if (event.key === "c" && (event.ctrlKey || event.metaKey) && !event.shiftKey) {
        event.preventDefault();
        void onStop();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
    };
  }, [busy, client, repositoryId]);

  useEffect(() => {
    if (!busy || !repositoryId) {
      return;
    }
    let cancelled = false;
    const pull = () => {
      void client.watchWorkspaceCommand(repositoryId).then((snapshot) => {
        if (cancelled) {
          return;
        }
        if (snapshot.running === true || snapshot.output !== "") {
          setRun(snapshot);
        }
      }, () => undefined);
    };
    pull();
    const timer = window.setInterval(pull, 150);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [busy, client, repositoryId]);

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

  const status = runStatus(run, busy);

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
            className="terminal-page__input"
            value={draft}
            aria-label="Command"
            placeholder="npm test"
            disabled={busy}
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
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void onRun();
              }
            }}
          />
        </label>
        <button
          type="button"
          className="btn-primary"
          disabled={busy || draft.trim() === ""}
          onClick={() => {
            void onRun();
          }}
        >
          {busy ? "Running" : "Run"}
        </button>
        {busy ? (
          <button type="button" className="btn-quiet" onClick={() => void onStop()}>
            Stop
          </button>
        ) : null}
      </div>
      <pre
        ref={outputRef}
        className="terminal-page__output"
        data-empty={run && (busy || run.output !== "") ? undefined : "true"}
      >
        {run?.output !== undefined && run.output !== ""
          ? run.output
          : busy
            ? ""
            : "Run a command in this workspace."}
      </pre>
    </section>
  );
}

function runStatus(run: WorkspaceTerminalRun | null, busy: boolean): string | null {
  if (busy) {
    return "Running.";
  }
  if (!run) {
    return null;
  }
  if (run.cancelled) {
    return "Stopped.";
  }
  if (run.timedOut) {
    return "The command timed out.";
  }
  if (run.exitCode === null) {
    return "Finished.";
  }
  return `Exit ${run.exitCode}`;
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
