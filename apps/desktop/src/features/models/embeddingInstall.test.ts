// SPDX-License-Identifier: AGPL-3.0-or-later

import { describe, expect, it } from "vitest";

import {
  embeddingInstallProgressLabel,
  embeddingInstallProgressPercent,
  type EmbeddingInstallStatus,
} from "./embeddingInstall";

function status(overrides: Partial<EmbeddingInstallStatus> = {}): EmbeddingInstallStatus {
  return {
    state: "downloading",
    bytesDone: 0,
    bytesTotal: 0,
    modelKey: "minilm-l6-v2",
    ...overrides,
  };
}

describe("embeddingInstallProgressPercent", () => {
  it("returns null when total bytes are unknown", () => {
    expect(embeddingInstallProgressPercent(status())).toBeNull();
  });

  it("returns a rounded percentage when progress is known", () => {
    expect(
      embeddingInstallProgressPercent(
        status({ bytesDone: 250, bytesTotal: 1000 }),
      ),
    ).toBe(25);
    expect(
      embeddingInstallProgressPercent(
        status({ bytesDone: 999, bytesTotal: 1000 }),
      ),
    ).toBe(100);
  });
});

describe("embeddingInstallProgressLabel", () => {
  it("renders a text percentage while downloading", () => {
    expect(
      embeddingInstallProgressLabel(
        status({ bytesDone: 512, bytesTotal: 1024 }),
      ),
    ).toBe("50%");
  });

  it("falls back to verifying copy without a total", () => {
    expect(
      embeddingInstallProgressLabel(
        status({ state: "verifying", bytesDone: 1024, bytesTotal: 1024 }),
      ),
    ).toBe("100%");
  });
});
