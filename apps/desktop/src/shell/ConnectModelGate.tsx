// SPDX-License-Identifier: AGPL-3.0-or-later

import { useState } from "react";
import type { ModelsClient } from "../features/models/client";

interface ConnectModelGateProps {
  modelsClient: ModelsClient;
  onConnected: () => void;
}

export function ConnectModelGate({ modelsClient, onConnected }: ConnectModelGateProps) {
  const [displayName, setDisplayName] = useState("Local model");
  const [baseUrl, setBaseUrl] = useState("http://127.0.0.1:11434/v1");
  const [apiKey, setApiKey] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit() {
    setError(null);
    setBusy(true);
    try {
      const created = await modelsClient.createProvider({
        kind: "openai_compatible",
        displayName: displayName.trim() || "Local model",
        baseUrl: baseUrl.trim() || null,
        billed: false,
        apiKey: apiKey.trim() ? apiKey.trim() : null,
      });
      const byRole = Object.fromEntries(
        created.profiles.map((profile) => [profile.role, profile.id]),
      );
      const planner = byRole.planner ?? created.profiles[0]?.id;
      const coder = byRole.coder ?? planner;
      const reviewer = byRole.reviewer ?? planner;
      const embedding = byRole.embedding ?? planner;
      if (!planner || !coder || !reviewer || !embedding) {
        setError("The provider did not create model roles. Try again.");
        return;
      }
      await modelsClient.assign(
        { planner, coder, reviewer, embedding },
        { confirmSharedRoles: true },
      );
      onConnected();
    } catch {
      setError("Could not save the model. Check the URL and key, then try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="gate">
      <h1 className="gate__title">Connect a model</h1>
      <p className="gate__body">
        Kronos needs one model before it can chat. The key is stored by the operating system, not
        in this window.
      </p>
      <form
        className="gate__form"
        onSubmit={(event) => {
          event.preventDefault();
          void onSubmit();
        }}
      >
        <label className="wizard__label" htmlFor="model-name">
          Name
          <input
            id="model-name"
            className="wizard__input"
            value={displayName}
            onChange={(event) => {
              setDisplayName(event.target.value);
            }}
          />
        </label>
        <label className="wizard__label" htmlFor="model-url">
          API URL
          <input
            id="model-url"
            className="wizard__input"
            value={baseUrl}
            onChange={(event) => {
              setBaseUrl(event.target.value);
            }}
          />
        </label>
        <label className="wizard__label" htmlFor="model-key">
          API key (optional for local servers)
          <input
            id="model-key"
            className="wizard__input"
            type="password"
            autoComplete="off"
            value={apiKey}
            onChange={(event) => {
              setApiKey(event.target.value);
            }}
          />
        </label>
        {error ? <p className="wizard__error">{error}</p> : null}
        <button type="submit" className="btn-primary" disabled={busy}>
          Continue
        </button>
        <p className="gate__hint">Cursor CLI is optional. You can add it later in Settings.</p>
      </form>
    </section>
  );
}
