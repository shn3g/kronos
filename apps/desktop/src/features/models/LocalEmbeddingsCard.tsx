// SPDX-License-Identifier: AGPL-3.0-or-later

import { useEffect, useRef, useState } from "react";

import {
  embeddingInstallProgressLabel,
  embeddingInstallProgressPercent,
  type EmbeddingCatalogItem,
  type EmbeddingInstallSnapshot,
  type EmbeddingInstallStatus,
} from "./embeddingInstall";
import type { ModelsClient } from "./client";

interface LocalEmbeddingsCardProps {
  modelsClient: ModelsClient;
  variant?: "settings" | "gate";
  onReady?: () => void;
}

const POLL_MS = 500;

function embeddingsInstalled(snapshot: EmbeddingInstallSnapshot): boolean {
  return snapshot.activeKey !== null || snapshot.catalog.some((item) => item.installed);
}

export function LocalEmbeddingsCard({
  modelsClient,
  variant = "settings",
  onReady,
}: LocalEmbeddingsCardProps) {
  const [snapshot, setSnapshot] = useState<EmbeddingInstallSnapshot | null>(null);
  const [selectedKey, setSelectedKey] = useState("minilm-l6-v2");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const readyFired = useRef(false);
  const onReadyRef = useRef(onReady);
  onReadyRef.current = onReady;

  useEffect(() => {
    let cancelled = false;
    const refresh = async () => {
      try {
        const next = await modelsClient.embeddingInstall();
        if (cancelled) {
          return;
        }
        setSnapshot(next);
        if (next.activeKey) {
          setSelectedKey(next.activeKey);
        } else if (next.catalog.length > 0) {
          setSelectedKey((current) => current || next.catalog[0]?.key || "minilm-l6-v2");
        }
        if (embeddingsInstalled(next) && onReadyRef.current && !readyFired.current) {
          readyFired.current = true;
          onReadyRef.current();
        }
      } catch {
        if (!cancelled) {
          setError("Could not load local embedding install status.");
        }
      }
    };
    void refresh();
    const interval = window.setInterval(() => {
      void refresh();
    }, POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [modelsClient]);

  const status = snapshot?.status;
  const installing =
    status?.state === "downloading" || status?.state === "verifying";
  const selected = snapshot?.catalog.find((item) => item.key === selectedKey);
  const installed = selected?.installed === true;
  const progressPercent =
    status && installing ? embeddingInstallProgressPercent(status) : null;
  const gate = variant === "gate";

  async function onInstall() {
    if (!selectedKey) {
      return;
    }
    setError(null);
    setBusy(true);
    try {
      const next = await modelsClient.startEmbeddingInstall(selectedKey);
      setSnapshot(next);
    } catch {
      setError("Install failed. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  }

  async function onRemove() {
    if (!selectedKey) {
      return;
    }
    setError(null);
    setBusy(true);
    try {
      const next = await modelsClient.removeEmbeddingInstall(selectedKey);
      setSnapshot(next);
    } catch {
      setError("Could not remove the installed embedding model.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section
      className={gate ? "gate__embeddings" : "models__embeddings"}
      aria-labelledby={gate ? undefined : "local-embeddings-title"}
    >
      {gate ? null : (
        <h2 id="local-embeddings-title" className="models__embeddings-title">
          Local embeddings
        </h2>
      )}
      <p className="page-body">
        {snapshot?.policy ??
          "Kronos downloads model weights only when you click Install, from pinned URLs verified by SHA-256."}
      </p>
      <label className="models__field" htmlFor="embedding-model-key">
        Model
        <select
          id="embedding-model-key"
          value={selectedKey}
          disabled={installing || busy}
          onChange={(event) => {
            setSelectedKey(event.target.value);
          }}
        >
          {(snapshot?.catalog ?? []).map((item: EmbeddingCatalogItem) => (
            <option key={item.key} value={item.key}>
              {item.displayName} ({item.dim}d)
              {item.installed ? " — installed" : ""}
            </option>
          ))}
        </select>
      </label>
      <div className="models__embeddings-actions">
        <button
          type="button"
          className={gate ? "btn-primary" : "btn-quiet"}
          disabled={installing || busy || installed}
          onClick={() => {
            void onInstall();
          }}
        >
          Install
        </button>
        {gate ? null : (
          <button
            type="button"
            className="btn-quiet"
            disabled={installing || busy || !installed}
            onClick={() => {
              void onRemove();
            }}
          >
            Remove
          </button>
        )}
      </div>
      {installing && status ? <InstallProgress status={status} percent={progressPercent} /> : null}
      {status?.state === "failed" && status.error ? (
        <p className="wizard__error" role="alert">
          {status.error}
        </p>
      ) : null}
      {status?.state === "ready" && status.modelKey === selectedKey ? (
        <p className="models__saved">Local embeddings are ready.</p>
      ) : null}
      {error ? (
        <p className="wizard__error" role="alert">
          {error}
        </p>
      ) : null}
    </section>
  );
}

function InstallProgress({
  status,
  percent,
}: {
  status: EmbeddingInstallStatus;
  percent: number | null;
}) {
  const width = percent ?? 0;
  return (
    <div className="models__embeddings-progress" aria-live="polite">
      <progress
        className="models__embeddings-progress-bar"
        max={100}
        value={percent ?? undefined}
        aria-label={`Install progress ${width} percent`}
      />
      <span className="models__embeddings-progress-label">
        {embeddingInstallProgressLabel(status)}
      </span>
    </div>
  );
}
