// SPDX-License-Identifier: AGPL-3.0-or-later

import { useState } from "react";
import { writeClipboardText } from "../features/chat/writeClipboardText";

interface EngineGateProps {
  starting: boolean;
  crashLog?: string | null;
}

export function EngineGate({ starting, crashLog }: EngineGateProps) {
  if (starting) {
    return (
      <section className="gate">
        <p className="gate__brand">Kronos</p>
        <h1 className="gate__title">Starting Kronos</h1>
        <p className="gate__body">This usually takes a few seconds.</p>
      </section>
    );
  }
  const log = crashLog?.trim() ? crashLog : null;
  return (
    <section className="gate">
      <p className="gate__brand">Kronos</p>
      <h1 className="gate__title">Kronos stopped unexpectedly</h1>
      <p className="gate__body">
        {log
          ? "Kronos is restarting. If this keeps happening, copy the details below and open an issue."
          : "Kronos is restarting. If this keeps happening, quit and reopen the app."}
      </p>
      {log ? <CrashDetails log={log} /> : null}
    </section>
  );
}

function CrashDetails({ log }: { log: string }) {
  const [copyState, setCopyState] = useState<"idle" | "copied" | "error">("idle");

  async function onCopy(): Promise<void> {
    const ok = await writeClipboardText(log);
    setCopyState(ok ? "copied" : "error");
  }

  return (
    <>
      <details className="gate__details">
        <summary>Show details</summary>
        <pre className="gate__log">{log}</pre>
      </details>
      <div className="gate__details-actions">
        <button type="button" className="btn-quiet" onClick={() => void onCopy()}>
          {copyState === "copied" ? "Copied" : "Copy details"}
        </button>
        {copyState === "error" ? (
          <p className="gate__hint" role="status">
            Could not copy. Select the text and copy it yourself.
          </p>
        ) : null}
      </div>
    </>
  );
}

export function CheckingModelGate({ label }: { label?: string }) {
  return (
    <section className="gate">
      <h1 className="gate__title">{label ?? "Checking the model connection"}</h1>
      <p className="gate__body">
        {label
          ? "Looking up local embedding install status."
          : "Looking up the assigned model."}
      </p>
    </section>
  );
}
