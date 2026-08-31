// SPDX-License-Identifier: AGPL-3.0-or-later

import { useEffect, useState } from "react";
import type { EngineClient } from "../../../engine/client";
import {
  createProductionTelegramClient,
  type TelegramClient,
  type TelegramStatus,
} from "./client";

export type { TelegramClient } from "./client";

const productionTelegram = createProductionTelegramClient();

interface TelegramPageProps {
  engineClient: EngineClient;
  telegramClient?: TelegramClient;
}

export function TelegramPage({ engineClient, telegramClient }: TelegramPageProps) {
  const client = telegramClient ?? productionTelegram;
  const [ready, setReady] = useState(false);
  const [status, setStatus] = useState<TelegramStatus | null>(null);
  const [userIds, setUserIds] = useState("");
  const [chatIds, setChatIds] = useState("");
  const [defaultRepo, setDefaultRepo] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const apply = () => {
      void engineClient.getState().then((state) => {
        if (!cancelled) {
          setReady(state.status === "ready");
        }
      });
    };
    apply();
    const interval = window.setInterval(apply, 1500);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [engineClient]);

  useEffect(() => {
    if (!ready) {
      return;
    }
    let cancelled = false;
    void client.status().then((next) => {
      if (cancelled) {
        return;
      }
      setStatus(next);
      setUserIds(next.allowedUserIds.join(", "));
      setChatIds(next.allowedChatIds.join(", "));
      setDefaultRepo(next.defaultRepositoryId ?? "");
    });
    return () => {
      cancelled = true;
    };
  }, [client, ready]);

  if (!ready) {
    return (
      <section className="telegram-setup">
        <h2 className="wizard__title">Telegram</h2>
        <p className="page-body">
          Connect a compatible engine to set up Telegram. Setup stays closed until the local engine
          is ready.
        </p>
      </section>
    );
  }

  async function onImportToken() {
    setError(null);
    try {
      await client.importBotToken();
      setStatus(await client.status());
    } catch {
      setError("Could not import the Telegram bot token from a file.");
    }
  }

  async function onSaveAllowlist() {
    setError(null);
    try {
      await client.saveAllowlist({
        allowedUserIds: parseUserIds(userIds),
        allowedChatIds: parseChatIds(chatIds),
        defaultRepositoryId: defaultRepo.trim() || null,
      });
      setStatus(await client.status());
    } catch {
      setError("Could not save the Telegram allowlist.");
    }
  }

  return (
    <section className="telegram-setup">
      <h2 className="wizard__title">Telegram</h2>
      <p className="page-body">
        Telegram is a first-party connector. Approved users create goals and observe work through
        the same engine services as this desktop.
      </p>
      <p className="github-setup__meta">
        <a href={status?.botfatherUrl ?? "https://t.me/BotFather"} target="_blank" rel="noreferrer">
          Open BotFather
        </a>
      </p>
      <ul className="github-setup__checks">
        {(status?.setupSteps ?? []).map((step) => (
          <li key={step}>{step}</li>
        ))}
      </ul>
      <p className="github-setup__meta">Token stored: {status?.tokenPresent ? "yes" : "no"}</p>
      <button type="button" className="btn-primary" onClick={() => void onImportToken()}>
        Import bot token from file
      </button>
      <form
        className="wizard"
        onSubmit={(event) => {
          event.preventDefault();
          void onSaveAllowlist();
        }}
      >
        <label className="wizard__label" htmlFor="telegram-user-ids">
          Allowed user IDs
          <input
            id="telegram-user-ids"
            className="wizard__input"
            value={userIds}
            onChange={(event) => setUserIds(event.target.value)}
          />
        </label>
        <label className="wizard__label" htmlFor="telegram-chat-ids">
          Allowed chat IDs
          <input
            id="telegram-chat-ids"
            className="wizard__input"
            value={chatIds}
            onChange={(event) => setChatIds(event.target.value)}
          />
        </label>
        <label className="wizard__label" htmlFor="telegram-default-repo">
          Default repository
          <input
            id="telegram-default-repo"
            className="wizard__input"
            value={defaultRepo}
            onChange={(event) => setDefaultRepo(event.target.value)}
          />
        </label>
        <button type="submit" className="btn-primary">
          Save allowlist
        </button>
      </form>
      {error ? <p className="wizard__error">{error}</p> : null}
    </section>
  );
}

function parseIntegerIds(raw: string): number[] {
  return raw
    .split(/[\s,]+/)
    .map((item) => Number(item))
    .filter((value) => Number.isFinite(value) && Number.isInteger(value) && value !== 0);
}

function parseUserIds(raw: string): number[] {
  return parseIntegerIds(raw).filter((value) => value > 0);
}

function parseChatIds(raw: string): number[] {
  return parseIntegerIds(raw);
}
