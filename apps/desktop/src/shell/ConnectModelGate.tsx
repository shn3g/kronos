// SPDX-License-Identifier: AGPL-3.0-or-later

import { useEffect, useState } from "react";
import type { DetectedTool, ModelsClient, ProviderDraft } from "../features/models/client";
import {
  assignmentsFromCreatedProfiles,
  billedFromBaseUrl,
  cursorCliDetected,
  displayNameFromEndpointLabel,
  hostedApiNeedsKey,
  localOpenAiProviderDraft,
  MODEL_URL_PRESETS,
  pickLocalOpenAiEndpoint,
} from "./connectModel";

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
  const [detected, setDetected] = useState<DetectedTool[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    void modelsClient.snapshot().then(
      (snapshot) => {
        if (cancelled) {
          return;
        }
        setDetected(snapshot.detected);
        const local = pickLocalOpenAiEndpoint(snapshot.detected);
        if (local) {
          setBaseUrl(local.label);
          setDisplayName(displayNameFromEndpointLabel(local.label));
        }
      },
      () => {
        if (!cancelled) {
          setDetected([]);
        }
      },
    );
    return () => {
      cancelled = true;
    };
  }, [modelsClient]);

  const localEndpoint = pickLocalOpenAiEndpoint(detected ?? []);
  const showCursorCliNote =
    detected !== null && cursorCliDetected(detected) && localEndpoint === null;

  async function registerProvider(draft: ProviderDraft): Promise<void> {
    setError(null);
    setBusy(true);
    try {
      const created = await modelsClient.createProvider(draft);
      const assignments = assignmentsFromCreatedProfiles(created.profiles);
      if (!assignments) {
        setError("The provider did not create model roles. Try again.");
        return;
      }
      await modelsClient.assign(assignments, { confirmSharedRoles: true });
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
      {detected === null ? (
        <p className="gate__hint">Looking for a local model server.</p>
      ) : null}
      {localEndpoint ? (
        <div className="gate__found">
          <p>Found a local model server on this machine.</p>
          <button
            type="button"
            className="btn-primary"
            disabled={busy}
            onClick={() => {
              void registerProvider(localOpenAiProviderDraft(localEndpoint));
            }}
          >
            Use {localEndpoint.label}
          </button>
        </div>
      ) : null}
      {showCursorCliNote ? (
        <div className="gate__note">
          <p>Cursor CLI is on this machine. It can run unattended goals later.</p>
          <p>
            Chat still needs a model API such as Ollama, LM Studio, or a hosted OpenAI-compatible
            key.
          </p>
        </div>
      ) : null}
      <form
        className="gate__form"
        onSubmit={(event) => {
          event.preventDefault();
          if (hostedApiNeedsKey(baseUrl, apiKey)) {
            setError("A hosted API needs a key.");
            return;
          }
          void registerProvider({
            kind: "openai_compatible",
            displayName: displayName.trim() || "Local model",
            baseUrl: baseUrl.trim() || null,
            billed: false,
            apiKey: apiKey.trim() ? apiKey.trim() : null,
          });
        }}
      >
        <p className="gate__form-title">{localEndpoint ? "Or enter a different URL" : "Model API"}</p>
        <div className="gate__presets" role="group" aria-label="Common model APIs">
          {MODEL_URL_PRESETS.map((preset) => (
            <button
              key={preset.id}
              type="button"
              className="btn-quiet"
              aria-pressed={baseUrl === preset.url}
              disabled={busy}
              onClick={() => {
                setDisplayName(preset.label);
                setBaseUrl(preset.url);
                setError(null);
              }}
            >
              {preset.label}
            </button>
          ))}
        </div>
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
          API key{billedFromBaseUrl(baseUrl) ? "" : " (optional for local servers)"}
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
        {showCursorCliNote ? null : (
          <p className="gate__hint">
            Typical local URLs are Ollama on port 11434 and LM Studio on port 1234.
          </p>
        )}
      </form>
    </section>
  );
}
