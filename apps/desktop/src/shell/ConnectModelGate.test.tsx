// SPDX-License-Identifier: AGPL-3.0-or-later

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ModelsClient } from "../features/models/client";
import { ConnectModelGate } from "./ConnectModelGate";

function modelsClient(overrides: Partial<ModelsClient> = {}): ModelsClient {
  return {
    snapshot: async () => ({
      detected: [],
      profiles: [],
      assignments: {
        planner: null,
        coder: null,
        reviewer: null,
        embedding: null,
      },
    }),
    assign: async () => ({
      planner: "prof_1",
      coder: "prof_1",
      reviewer: "prof_1",
      embedding: "prof_1",
    }),
    createProvider: async () => ({
      provider: {
        id: "prov_1",
        kind: "openai_compatible",
        displayName: "Local",
        billed: false,
      },
      profiles: [{ id: "prof_1", displayName: "Local (planner)", role: "planner", billed: false }],
    }),
    ...overrides,
  };
}

describe("ConnectModelGate", () => {
  it("offers one-click use of a detected local OpenAI server", async () => {
    const user = userEvent.setup();
    const createProvider = vi.fn(async (draft: { baseUrl: string | null }) => ({
      provider: {
        id: "prov_1",
        kind: "openai_compatible",
        displayName: draft.baseUrl ?? "Local",
        billed: false,
      },
      profiles: [{ id: "prof_1", displayName: "Local (planner)", role: "planner", billed: false }],
    }));
    const assign = vi.fn(async () => ({
      planner: "prof_1",
      coder: "prof_1",
      reviewer: "prof_1",
      embedding: "prof_1",
    }));
    const onConnected = vi.fn();
    render(
      <ConnectModelGate
        modelsClient={modelsClient({
          snapshot: async () => ({
            detected: [
              { kind: "openai_compatible", label: "http://127.0.0.1:11434/v1", present: true },
            ],
            profiles: [],
            assignments: {
              planner: null,
              coder: null,
              reviewer: null,
              embedding: null,
            },
          }),
          createProvider,
          assign,
        })}
        onConnected={onConnected}
      />,
    );

    await user.click(await screen.findByRole("button", { name: /use http:\/\/127\.0\.0\.1:11434\/v1/i }));
    expect(createProvider).toHaveBeenCalledWith(
      expect.objectContaining({
        kind: "openai_compatible",
        baseUrl: "http://127.0.0.1:11434/v1",
        billed: false,
      }),
    );
    expect(assign).toHaveBeenCalled();
    expect(onConnected).toHaveBeenCalled();
  });

  it("fills a hosted OpenAI URL from a preset and requires a key", async () => {
    const user = userEvent.setup();
    const createProvider = vi.fn(async (draft: { baseUrl: string | null; billed: boolean }) => ({
      provider: {
        id: "prov_1",
        kind: "openai_compatible",
        displayName: "OpenAI",
        billed: draft.billed,
      },
      profiles: [{ id: "prof_1", displayName: "OpenAI (planner)", role: "planner", billed: false }],
    }));
    const assign = vi.fn(async () => ({
      planner: "prof_1",
      coder: "prof_1",
      reviewer: "prof_1",
      embedding: "prof_1",
    }));
    render(
      <ConnectModelGate
        modelsClient={modelsClient({ createProvider, assign })}
        onConnected={() => undefined}
      />,
    );

    await user.click(await screen.findByRole("button", { name: /^openai$/i }));
    expect(screen.getByRole("button", { name: /^openai$/i })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByLabelText(/^name$/i)).toHaveValue("OpenAI");
    expect(screen.getByLabelText(/api url/i)).toHaveValue("https://api.openai.com/v1");
    await user.click(screen.getByRole("button", { name: /^continue$/i }));
    expect(createProvider).not.toHaveBeenCalled();
    expect(screen.getByText(/hosted api needs a key/i)).toBeInTheDocument();
    await user.type(screen.getByLabelText(/^api key$/i), "sk-test");
    await user.click(screen.getByRole("button", { name: /^continue$/i }));
    expect(createProvider).toHaveBeenCalledWith(
      expect.objectContaining({
        billed: false,
        baseUrl: "https://api.openai.com/v1",
        apiKey: "sk-test",
      }),
    );
    expect(assign).toHaveBeenCalled();
  });

  it("says Cursor CLI cannot chat until a model API is connected", async () => {
    render(
      <ConnectModelGate
        modelsClient={modelsClient({
          snapshot: async () => ({
            detected: [{ kind: "cursor_cli", label: "cursor-agent", present: true }],
            profiles: [],
            assignments: {
              planner: null,
              coder: null,
              reviewer: null,
              embedding: null,
            },
          }),
        })}
        onConnected={() => undefined}
      />,
    );

    expect(
      await screen.findByText(/cursor cli is on this machine/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/chat still needs a model api/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /use http/i })).not.toBeInTheDocument();
  });
});
