// SPDX-License-Identifier: AGPL-3.0-or-later

import { LocalEmbeddingsCard } from "../features/models/LocalEmbeddingsCard";
import type { ModelsClient } from "../features/models/client";

interface EmbeddingsGateProps {
  modelsClient: ModelsClient;
  onReady: () => void;
}

export function EmbeddingsGate({ modelsClient, onReady }: EmbeddingsGateProps) {
  return (
    <section className="gate">
      <p className="gate__step">Step 2 of 3 · Install local embeddings</p>
      <h1 className="gate__title">Install local embeddings</h1>
      <p className="gate__body">
        Kronos needs a local embedding model for code search and @-mentions. Weights download once
        and are verified by SHA-256.
      </p>
      <LocalEmbeddingsCard modelsClient={modelsClient} variant="gate" onReady={onReady} />
    </section>
  );
}
