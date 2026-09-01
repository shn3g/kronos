// SPDX-License-Identifier: AGPL-3.0-or-later

import { useEffect, useState } from "react";
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
      </div>
      <pre className="terminal-page__output" data-empty={run ? undefined : "true"}>
        {run?.output ?? "Run a command in this workspace."}
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
  if (run.timedOut) {
    return "The command timed out.";
  }
  if (run.exitCode === null) {
    return "Finished.";
  }
  return `Exit ${run.exitCode}`;
}
