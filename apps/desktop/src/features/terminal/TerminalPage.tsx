// SPDX-License-Identifier: AGPL-3.0-or-later

import { useEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import type { Terminal } from "@xterm/xterm";
import type { EngineClient } from "../../engine/client";
import {
  createProductionRepositoriesClient,
  type RepositoriesClient,
  type WorkspaceTerminalRun,
} from "../workspaces/client";
import { ptyInputFromKeyboard, xtermCanvasIsUsable } from "./terminalInput";

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
  const [error, setError] = useState<string | null>(null);
  const [run, setRun] = useState<WorkspaceTerminalRun | null>(null);
  const [xtermMode, setXtermMode] = useState(false);
  const stoppingRef = useRef(false);
  const hostRef = useRef<HTMLDivElement | null>(null);
  const termRef = useRef<Terminal | null>(null);
  const runRef = useRef<WorkspaceTerminalRun | null>(null);
  const previousRepoRef = useRef<string | null>(null);
  const writtenRef = useRef("");
  const sendPtyRef = useRef<(data: string) => Promise<void>>(async () => undefined);
  runRef.current = run;

  async function sendPty(data: string): Promise<void> {
    if (!repositoryId || data === "") {
      return;
    }
    try {
      await client.writeWorkspaceShell(repositoryId, data);
    } catch {
      setError("Could not send that key. Check that the engine is running, then try again.");
    }
  }

  sendPtyRef.current = sendPty;

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
    if (!ready || !repositoryId || !xtermCanvasIsUsable()) {
      return;
    }
    let cancelled = false;
    let term: Terminal | null = null;
    let onFit: (() => void) | null = null;
    void (async () => {
      const { Terminal: Xterm } = await import("@xterm/xterm");
      const { FitAddon } = await import("@xterm/addon-fit");
      await import("@xterm/xterm/css/xterm.css");
      const host = hostRef.current;
      if (cancelled || host === null) {
        return;
      }
      const addon = new FitAddon();
      term = new Xterm({
        convertEol: true,
        cursorBlink: true,
        fontFamily: 'ui-monospace, "Cascadia Code", Consolas, monospace',
        fontSize: 13,
        theme: {
          background: "#050508",
          foreground: "#f4f4f6",
          cursor: "#ececef",
        },
      });
      term.loadAddon(addon);
      term.open(host);
      if (cancelled) {
        term.dispose();
        term = null;
        return;
      }
      const textarea = host.querySelector("textarea");
      if (textarea instanceof HTMLTextAreaElement) {
        textarea.setAttribute("aria-label", "Terminal");
      }
      term.onData((data) => {
        void sendPtyRef.current(data);
      });
      onFit = () => {
        addon.fit();
        if (term !== null) {
          void client.resizeWorkspaceShell(repositoryId, term.cols, term.rows);
        }
      };
      window.addEventListener("resize", onFit);
      addon.fit();
      void client.resizeWorkspaceShell(repositoryId, term.cols, term.rows);
      termRef.current = term;
      writtenRef.current = "";
      setXtermMode(true);
      term.focus();
    })();
    return () => {
      cancelled = true;
      if (onFit !== null) {
        window.removeEventListener("resize", onFit);
      }
      termRef.current = null;
      term?.dispose();
      setXtermMode(false);
    };
  }, [client, ready, repositoryId]);

  useEffect(() => {
    const term = termRef.current;
    if (term === null || !xtermMode) {
      return;
    }
    const output = run?.output ?? "";
    if (output.startsWith(writtenRef.current)) {
      term.write(output.slice(writtenRef.current.length));
    } else {
      term.reset();
      term.write(output);
    }
    writtenRef.current = output;
  }, [run?.output, xtermMode]);

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

  function onTerminalKey(event: ReactKeyboardEvent<HTMLTextAreaElement>): void {
    const data = ptyInputFromKeyboard(event);
    if (data === null) {
      return;
    }
    event.preventDefault();
    void sendPty(data);
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
          Open a workspace to run commands here.
        </p>
        <button type="button" className="btn-quiet" onClick={onOpenWorkspace}>
          Open folder
        </button>
      </section>
    );
  }

  const status = runStatus(run);
  const shellOpen = run?.running === true;
  const output = run?.output ?? "";

  return (
    <section className="terminal-page">
      <header className="terminal-page__head">
        <h2 className="terminal-page__title">Terminal</h2>
        {status ? (
          <p className="terminal-page__status" aria-live="polite">
            {status}
          </p>
        ) : null}
        {shellOpen ? (
          <button type="button" className="btn-quiet" onClick={() => void onStop()}>
            Stop
          </button>
        ) : null}
      </header>
      {error ? <p className="wizard__error">{error}</p> : null}
      <div className="terminal-page__screen">
        <div
          ref={hostRef}
          className={xtermMode ? "terminal-page__xterm is-on" : "terminal-page__xterm"}
          aria-hidden={!xtermMode}
        />
        <textarea
          className={xtermMode ? "terminal-page__tty is-off" : "terminal-page__tty"}
          aria-label="Terminal"
          spellCheck={false}
          value={output}
          placeholder="Type in this workspace shell."
          aria-hidden={xtermMode}
          tabIndex={xtermMode ? -1 : undefined}
          onChange={() => undefined}
          onKeyDown={onTerminalKey}
        />
      </div>
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
