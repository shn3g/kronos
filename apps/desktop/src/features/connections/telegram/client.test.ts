// SPDX-License-Identifier: AGPL-3.0-or-later
/** @vitest-environment node */

import { describe, expect, it } from "vitest";
import { createProductionTelegramClient } from "./client";

describe("createProductionTelegramClient", () => {
  it("loads status through the engine JSON proxy without a token field", async () => {
    const client = createProductionTelegramClient(async (method, path) => {
      expect(method).toBe("GET");
      expect(path).toBe("/telegram/status");
      return {
        status: 200,
        body: JSON.stringify({
          token_present: true,
          allowed_user_ids: [4242],
          allowed_chat_ids: [9001],
          default_repository_id: "repo_alpha",
          last_update_offset: 12,
          botfather_url: "https://t.me/BotFather",
          setup_steps: ["Open BotFather in Telegram and create a bot with /newbot."],
        }),
      };
    });

    await expect(client.status()).resolves.toEqual({
      tokenPresent: true,
      allowedUserIds: [4242],
      allowedChatIds: [9001],
      defaultRepositoryId: "repo_alpha",
      lastUpdateOffset: 12,
      botfatherUrl: "https://t.me/BotFather",
      setupSteps: ["Open BotFather in Telegram and create a bot with /newbot."],
    });
  });

  it("saves allowlist ids without sending a bot token", async () => {
    const bodies: unknown[] = [];
    const client = createProductionTelegramClient(async (method, path, body) => {
      bodies.push({ method, path, body });
      return { status: 200, body: JSON.stringify({ token_present: true }) };
    });
    await client.saveAllowlist({
      allowedUserIds: [1, 2],
      allowedChatIds: [9],
      defaultRepositoryId: "repo_alpha",
    });
    expect(bodies).toEqual([
      {
        method: "PUT",
        path: "/telegram/allowlist",
        body: {
          allowed_user_ids: [1, 2],
          allowed_chat_ids: [9],
          default_repository_id: "repo_alpha",
        },
      },
    ]);
    expect(JSON.stringify(bodies)).not.toMatch(/token|BEGIN RSA|private_key/i);
  });

  it("fails closed when the engine proxy is unavailable", async () => {
    const client = createProductionTelegramClient(async () => ({ status: 0, body: "" }));
    await expect(client.status()).rejects.toThrow(/engine/i);
  });
});
