// SPDX-License-Identifier: AGPL-3.0-or-later

export type EmbeddingInstallState =
  | "idle"
  | "downloading"
  | "verifying"
  | "ready"
  | "failed";

export interface EmbeddingInstallStatus {
  state: EmbeddingInstallState;
  bytesDone: number;
  bytesTotal: number;
  modelKey: string | null;
  error?: string | null;
}

export interface EmbeddingCatalogItem {
  key: string;
  dim: number;
  displayName: string;
  installed: boolean;
}

export interface EmbeddingInstallSnapshot {
  policy: string;
  catalog: EmbeddingCatalogItem[];
  activeKey: string | null;
  status: EmbeddingInstallStatus;
}

export function embeddingInstallProgressPercent(status: EmbeddingInstallStatus): number | null {
  if (status.bytesTotal <= 0) {
    return null;
  }
  const ratio = status.bytesDone / status.bytesTotal;
  if (!Number.isFinite(ratio)) {
    return null;
  }
  return Math.max(0, Math.min(100, Math.round(ratio * 100)));
}

export function embeddingInstallProgressLabel(status: EmbeddingInstallStatus): string {
  const percent = embeddingInstallProgressPercent(status);
  if (percent === null) {
    return status.state === "verifying" ? "Verifying…" : "Downloading…";
  }
  return `${percent}%`;
}
