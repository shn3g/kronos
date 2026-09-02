// SPDX-License-Identifier: AGPL-3.0-or-later

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { EngineClient } from "../../../engine/client";
import { TelegramPage, type TelegramClient } from "./TelegramPage";

function engine(status: "unavailable" | "starting" | "ready"): EngineClient {
  if (status === "ready") {
    return { getState: async () => ({ status: "ready", version: "0.1.0" }) };
  }
  return { getState: async () => ({ status }) };
}

function telegramClient(overrides: Partial<TelegramClient> = {}): TelegramClient {
  return {
    status: async () => ({
      tokenPresent: false,
      allowedUserIds: [],
      allowedChatIds: [],
      defaultRepositoryId: null,
      lastUpdateOffset: 0,
      botfatherUrl: "https://t.me/BotFather",
      setupSteps: [
        "Open BotFather in Telegram and create a bot with /newbot.",
        "Save the bot token in a local file. Do not paste it into the desktop WebView.",
      ],
    }),
    saveAllowlist: async () => ({ tokenPresent: true }),
    importBotToken: async () => ({ tokenPresent: true }),
    ...overrides,
  };
}

describe("TelegramPage", () => {
  it("stays fail-closed when the engine is not ready", async () => {
    const status = vi.fn(async () => telegramClient().status());
    render(
      <TelegramPage engineClient={engine("unavailable")} telegramClient={telegramClient({ status })} />,
    );

    expect(await screen.findByRole("heading", { name: "Telegram" })).toBeInTheDocument();
    expect(
      screen.getByText(/waiting for the engine/i),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /import bot token/i })).not.toBeInTheDocument();
    expect(status).not.toHaveBeenCalled();
  });

  it("guides BotFather setup without a token or PEM paste field", async () => {
    const user = userEvent.setup();
    const saveAllowlist = vi.fn(async () => ({ tokenPresent: true }));
    const importBotToken = vi.fn(async () => ({ tokenPresent: true }));
    const status = vi.fn(async () => ({
      ...(await telegramClient().status()),
      tokenPresent: true,
      allowedUserIds: [4242],
      allowedChatIds: [9001],
    }));
    render(
      <TelegramPage
        engineClient={engine("ready")}
        telegramClient={telegramClient({ saveAllowlist, importBotToken, status })}
      />,
    );

    expect(await screen.findByRole("heading", { name: "Telegram" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /botfather/i })).toHaveAttribute(
      "href",
      "https://t.me/BotFather",
    );
    expect(screen.queryByLabelText(/bot token/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/private key/i)).not.toBeInTheDocument();
    expect(await screen.findByText(/token stored:\s*yes/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /import bot token from file/i }));
    expect(importBotToken).toHaveBeenCalled();

    await user.clear(screen.getByLabelText(/allowed user ids/i));
    await user.type(screen.getByLabelText(/allowed user ids/i), "4242, 99");
    await user.clear(screen.getByLabelText(/allowed chat ids/i));
    await user.type(screen.getByLabelText(/allowed chat ids/i), "9001");
    await user.type(screen.getByLabelText(/default repository/i), "repo_alpha");
    await user.click(screen.getByRole("button", { name: /save allowlist/i }));
    expect(saveAllowlist).toHaveBeenCalledWith({
      allowedUserIds: [4242, 99],
      allowedChatIds: [9001],
      defaultRepositoryId: "repo_alpha",
    });
  });

  it("saves negative group chat ids on PUT allowlist and keeps user ids positive", async () => {
    const user = userEvent.setup();
    const saveAllowlist = vi.fn(async () => ({ tokenPresent: true }));
    render(
      <TelegramPage
        engineClient={engine("ready")}
        telegramClient={telegramClient({ saveAllowlist })}
      />,
    );

    expect(await screen.findByRole("heading", { name: "Telegram" })).toBeInTheDocument();
    await user.type(screen.getByLabelText(/allowed user ids/i), "4242, -7");
    await user.type(screen.getByLabelText(/allowed chat ids/i), "-100123");
    await user.click(screen.getByRole("button", { name: /save allowlist/i }));
    expect(saveAllowlist).toHaveBeenCalledWith({
      allowedUserIds: [4242],
      allowedChatIds: [-100123],
      defaultRepositoryId: null,
    });
  });
});
