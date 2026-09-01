// SPDX-License-Identifier: AGPL-3.0-or-later

import { useEffect, useState } from "react";
import {
  createProductionEngineClient,
  type EngineClient,
} from "../engine/client";
import { EngineStatus } from "../engine/EngineStatus";
import { WorkspacesPage } from "../features/workspaces/WorkspacesPage";
import { pickRepositoryFolder } from "../features/workspaces/client";
import { ModelsPage } from "../features/models/ModelsPage";
import { IndexPage } from "../features/index/IndexPage";
import { GitHubPage } from "../features/connections/github/GitHubPage";
import { TelegramPage } from "../features/connections/telegram/TelegramPage";
import { GoalsPage } from "../features/goals/GoalsPage";
import { ChatPage } from "../features/chat/ChatPage";
import { RunsPage } from "../features/runs/RunsPage";
import { SkillsPage } from "../features/skills/SkillsPage";
import { MemoryPage } from "../features/memory/MemoryPage";
import { HomePage } from "../features/home/HomePage";
import { SettingsPage } from "../features/settings/SettingsPage";
import { UpdatesPage } from "../features/updates/UpdatesPage";
import { NotificationsPage } from "../features/notifications/NotificationsPage";
import { pathFromHash, ROUTES } from "./routes";

const productionClient = createProductionEngineClient();

interface AppProps {
  engineClient?: EngineClient;
}

export function App({ engineClient }: AppProps) {
  const client = engineClient ?? productionClient;
  const [path, setPath] = useState(() => pathFromHash(window.location.hash));

  useEffect(() => {
    const onHashChange = () => {
      setPath(pathFromHash(window.location.hash));
    };
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">
        Skip to main content
      </a>
      <aside className="chrome-sidebar">
        <div className="brand">
          <p className="brand__mark">Kronos</p>
          <p className="brand__meta">Local engineering OS</p>
        </div>
        <nav className="chrome-nav" aria-label="Primary">
          {ROUTES.map((route) => (
            <a
              key={route.path}
              href={`#${route.path}`}
              className="chrome-nav__link"
              aria-current={route.path === path ? "page" : undefined}
            >
              {route.name}
            </a>
          ))}
        </nav>
      </aside>
      <div className="chrome-stage">
        <header className="chrome-topbar">
          <EngineStatus client={client} />
        </header>
        <main id="main" className="chrome-main" tabIndex={-1}>
          {path === "/workspaces" ? (
            <WorkspacesPage engineClient={client} pickFolder={pickRepositoryFolder} />
          ) : path === "/goals" ? (
            <GoalsPage engineClient={client} />
          ) : path === "/chat" ? (
            <ChatPage engineClient={client} />
          ) : path === "/runs" ? (
            <RunsPage engineClient={client} />
          ) : path === "/skills" ? (
            <SkillsPage engineClient={client} />
          ) : path === "/memory" ? (
            <MemoryPage engineClient={client} />
          ) : path === "/models" ? (
            <ModelsPage engineClient={client} />
          ) : path === "/index" ? (
            <IndexPage engineClient={client} />
          ) : path === "/connections" ? (
            <>
              <GitHubPage engineClient={client} />
              <TelegramPage engineClient={client} />
            </>
          ) : path === "/settings" ? (
            <SettingsPage engineClient={client} />
          ) : path === "/updates" ? (
            <UpdatesPage engineClient={client} />
          ) : path === "/notifications" ? (
            <NotificationsPage engineClient={client} />
          ) : (
            <HomePage engineClient={client} />
          )}
        </main>
      </div>
    </div>
  );
}
