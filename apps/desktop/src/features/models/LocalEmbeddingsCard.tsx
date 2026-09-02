// SPDX-License-Identifier: AGPL-3.0-or-later

import { useEffect, useState } from "react";

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
}

const POLL_MS = 500;

export function LocalEmbeddingsCard({ modelsClient }: LocalEmbeddingsCardProps) {
  const [snapshot, setSnapshot] = useState<EmbeddingInstallSnapshot | null>(null);
  const [selectedKey, setSelectedKey] = useState("minilm-l6-v2");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const refresh = async () => {
      try {
        const next = await modelsClient.embeddingInstall();
        if (!cancelled) {
          setSnapshot(next);
          if (next.activeKey) {
            setSelectedKey(next.activeKey);
          } else if (next.catalog.length > 0) {
            setSelectedKey((current) => current || next.catalog[0]?.key || "minilm-l6-v2");
          }
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
    <section className="models__embeddings" aria-labelledby="local-embeddings-title">
      <h2 id="local-embeddings-title" className="models__embeddings-title">
        Local embeddings
      </h2>
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
          className="btn-quiet"
          disabled={installing || busy || installed}
          onClick={() => {
            void onInstall();
          }}
        >
          Install
        </button>
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
