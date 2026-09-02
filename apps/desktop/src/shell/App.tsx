// SPDX-License-Identifier: AGPL-3.0-or-later

import { useEffect, useState } from "react";
import {
  createProductionEngineClient,
  type EngineClient,
  type EngineConnectionState,
} from "../engine/client";
import { EngineStatus } from "../engine/EngineStatus";
import { ChatPage } from "../features/chat/ChatPage";
import { createProductionChatClient, type ChatClient } from "../features/chat/client";
import { createProductionIndexClient, type IndexClient } from "../features/index/client";
import { GoalsPage, type GoalsPageClients } from "../features/goals/GoalsPage";
import { createProductionGoalsClient, type GoalsClient } from "../features/goals/client";
import { createProductionHomeClient, type HomeClient } from "../features/home/client";
import { createProductionModelsClient, type ModelsClient } from "../features/models/client";
import { RunsPage } from "../features/runs/RunsPage";
import { SettingsHub } from "../features/settings/SettingsHub";
import {
  createProductionSettingsClient,
  type SettingsPageClients,
} from "../features/settings/client";
import { WorkspacesPage } from "../features/workspaces/WorkspacesPage";
import {
  createProductionRepositoriesClient,
  pickRepositoryFolder,
  type RepositoriesClient,
} from "../features/workspaces/client";
import { ActivityBar, type ActivityId } from "./ActivityBar";
import { ConnectModelGate } from "./ConnectModelGate";
import { CheckingModelGate, EngineGate } from "./EngineGate";
import { InspectorDrawer, type InspectorTab } from "./InspectorDrawer";
import { MenuBar } from "./MenuBar";
import { hashFromRoute, routeFromHash, type SettingsSection, type ShellRoute } from "./routes";
import { shellShortcutFromKeyboard } from "./shellShortcut";
import { useSessionContext } from "./useSessionContext";
import { setDesktopWindowTitle } from "./windowTitle";
import { WorkspaceSwitcher } from "./WorkspaceSwitcher";

const productionEngine = createProductionEngineClient();
const productionModels = createProductionModelsClient();
const productionChat = createProductionChatClient();
const productionRepos = createProductionRepositoriesClient();
const productionHome = createProductionHomeClient();
const productionGoals = createProductionGoalsClient();
const productionSettings = createProductionSettingsClient();
const productionIndex = createProductionIndexClient();
const ACTIVITY_BAR_STORAGE_KEY = "kronos.activityBarCollapsed";
const INSPECTOR_STORAGE_KEY = "kronos.inspectorCollapsed";

function readFlag(key: string): boolean {
  if (typeof window === "undefined" || typeof window.localStorage === "undefined") {
    return false;
  }
  return window.localStorage.getItem(key) === "1";
}

function persistFlag(key: string, value: boolean): void {
  window.localStorage.setItem(key, value ? "1" : "0");
}

interface AppProps {
  engineClient?: EngineClient;
  modelsClient?: ModelsClient;
  chatClient?: ChatClient;
  repositoriesClient?: RepositoriesClient;
  homeClient?: HomeClient;
  goalsClient?: GoalsClient;
  settingsClient?: SettingsPageClients;
  indexClient?: IndexClient;
}

export function App({
  engineClient,
  modelsClient,
  chatClient,
  repositoriesClient,
  homeClient,
  goalsClient,
  settingsClient,
  indexClient,
}: AppProps) {
  const engine = engineClient ?? productionEngine;
  const models = modelsClient ?? productionModels;
  const chat = chatClient ?? productionChat;
  const repos = repositoriesClient ?? productionRepos;
  const home = homeClient ?? productionHome;
  const goals = goalsClient ?? productionGoals;
  const settings = settingsClient ?? productionSettings;
  const index = indexClient ?? productionIndex;
  const [engineState, setEngineState] = useState<EngineConnectionState>({
    status: "starting",
  });
  const [modelReady, setModelReady] = useState(false);
  const [modelKnown, setModelKnown] = useState(false);
  const [route, setRoute] = useState<ShellRoute>(() => routeFromHash(window.location.hash));
  const [historyOpen, setHistoryOpen] = useState(false);
  const [newChatRequest, setNewChatRequest] = useState(0);
  const [orchestratorName, setOrchestratorName] = useState<string | null>(null);
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>("changes");
  const [activityCollapsed, setActivityCollapsed] = useState(() =>
    readFlag(ACTIVITY_BAR_STORAGE_KEY),
  );
  const [inspectorCollapsed, setInspectorCollapsed] = useState(() =>
    readFlag(INSPECTOR_STORAGE_KEY),
  );

  useEffect(() => {
    let cancelled = false;
    const apply = () => {
      void engine.getState().then(
        (next) => {
          if (!cancelled) {
            setEngineState(next);
          }
        },
        () => {
          if (!cancelled) {
            setEngineState({ status: "unavailable" });
          }
        },
      );
    };
    apply();
    const interval = window.setInterval(apply, 1500);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [engine]);

  const engineReady = engineState.status === "ready";

  useEffect(() => {
    if (!engineReady) {
      setModelReady(false);
      setModelKnown(false);
      return;
    }
    let cancelled = false;
    void models.snapshot().then((snapshot) => {
      if (cancelled) {
        return;
      }
      const assigned = snapshot.assignments.orchestrator;
      setModelReady(Boolean(assigned));
      setModelKnown(true);
      const profile = snapshot.profiles.find((item) => item.id === assigned);
      setOrchestratorName(profile?.displayName ?? null);
    });
    return () => {
      cancelled = true;
    };
  }, [engineReady, engineState.status, models]);

  const session = useSessionContext({
    engineReady,
    modelReady,
    repositoriesClient: repos,
    homeClient: home,
    goalsClient: goals,
  });

  useEffect(() => {
    const onHashChange = () => {
      setRoute(routeFromHash(window.location.hash));
    };
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  function go(next: Partial<ShellRoute>): void {
    const merged: ShellRoute = {
      activity: next.activity ?? route.activity,
      settingsSection: next.settingsSection ?? route.settingsSection,
    };
    setRoute(merged);
    const hash = hashFromRoute(merged);
    if (window.location.hash !== hash) {
      window.location.hash = hash;
    }
  }

  function startNewChat(): void {
    go({ activity: "chat" });
    setNewChatRequest((current) => current + 1);
  }

  function openFiles(): void {
    go({ activity: "files" });
  }

  function toggleActivityBar(): void {
    setActivityCollapsed((current) => {
      const next = !current;
      persistFlag(ACTIVITY_BAR_STORAGE_KEY, next);
      return next;
    });
  }

  function toggleInspector(): void {
    setInspectorCollapsed((current) => {
      const next = !current;
      persistFlag(INSPECTOR_STORAGE_KEY, next);
      return next;
    });
  }

  useEffect(() => {
    if (!engineReady || !modelKnown || !modelReady) {
      return;
    }
    const expected = hashFromRoute(route);
    if (window.location.hash !== expected) {
      window.location.hash = expected;
    }
  }, [engineReady, modelKnown, modelReady, route]);

  useEffect(() => {
    if (!engineReady || !modelKnown || !modelReady) {
      return;
    }
    const onKey = (event: KeyboardEvent) => {
      const action = shellShortcutFromKeyboard(event);
      if (!action) {
        return;
      }
      if (
        action === "toggle-terminal" ||
        action === "go-to-file" ||
        action === "find-in-files" ||
        action === "ask-in-chat"
      ) {
        if (action === "go-to-file" || action === "find-in-files") {
          event.preventDefault();
          openFiles();
        }
        if (action === "ask-in-chat") {
          event.preventDefault();
          go({ activity: "chat" });
        }
        return;
      }
      event.preventDefault();
      if (action === "new-chat") {
        startNewChat();
        return;
      }
      if (action === "toggle-activity-bar") {
        toggleActivityBar();
        return;
      }
      if (action === "toggle-inspector") {
        toggleInspector();
        return;
      }
      go({ activity: "settings", settingsSection: "general" });
    };
    window.addEventListener("keydown", onKey, true);
    return () => {
      window.removeEventListener("keydown", onKey, true);
    };
  }, [engineReady, modelKnown, modelReady, route]);

  useEffect(() => {
    if (!engineReady || !modelKnown || !modelReady) {
      return;
    }
    const repo = session.repositories.find((item) => item.id === session.workspaceId);
    const title = repo ? `Kronos — ${repo.displayName}` : "Kronos";
    void setDesktopWindowTitle(title);
  }, [engineReady, modelKnown, modelReady, session.repositories, session.workspaceId]);

  if (engineState.status !== "ready") {
    return (
      <div className="app-shell app-shell--gate">
        <a className="skip-link" href="#main">
          Skip to main content
        </a>
        <EngineStatus state={engineState} />
        <main id="main" tabIndex={-1}>
          <EngineGate starting={engineState.status === "starting"} />
        </main>
      </div>
    );
  }

  if (modelKnown && !modelReady) {
    return (
      <div className="app-shell app-shell--gate">
        <a className="skip-link" href="#main">
          Skip to main content
        </a>
        <EngineStatus state={engineState} />
        <main id="main" tabIndex={-1}>
          <ConnectModelGate
            modelsClient={models}
            onConnected={() => {
              setModelReady(true);
            }}
          />
        </main>
      </div>
    );
  }

  if (!modelKnown) {
    return (
      <div className="app-shell app-shell--gate">
        <EngineStatus state={engineState} />
        <main id="main">
          <CheckingModelGate />
        </main>
      </div>
    );
  }

  const activity: ActivityId = route.activity;
  const goalsPageClient: GoalsPageClients = {
    ...goals,
    listRepositories: () => repos.list(),
  };
  const workspaceId = session.workspaceId;

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">
        Skip to main content
      </a>
      <MenuBar
        historyOpen={historyOpen}
        activityCollapsed={activityCollapsed}
        inspectorCollapsed={inspectorCollapsed}
        onNewChat={startNewChat}
        onOpenWorkspace={() => {
          go({ activity: "workspaces" });
        }}
        onGoToFile={openFiles}
        onFindInFile={openFiles}
        onFindInFiles={openFiles}
        onReplaceInFile={openFiles}
        onGoToLine={openFiles}
        onAskInChat={() => {
          go({ activity: "chat" });
        }}
        onToggleHistory={() => {
          setHistoryOpen((open) => !open);
        }}
        onToggleActivityBar={toggleActivityBar}
        onToggleInspector={toggleInspector}
        onOpenSettings={() => {
          go({ activity: "settings", settingsSection: "general" });
        }}
        onOpenModels={() => {
          go({ activity: "settings", settingsSection: "models" });
        }}
      />
      <div className="app-body" data-rail-collapsed={activityCollapsed ? "true" : "false"}>
        <ActivityBar
          active={activity}
          collapsed={activityCollapsed}
          onSelect={(id) => {
            go({ activity: id });
          }}
        />
        <div className="app-stage">
          <header className="title-bar">
            <WorkspaceSwitcher
              repositories={session.repositories}
              workspaceId={session.workspaceId}
              onChange={session.setWorkspaceId}
              onOpenFolder={() => {
                go({ activity: "workspaces" });
              }}
            />
            <EngineStatus state={engineState} />
          </header>
          <div
            className="app-columns"
            data-inspector-collapsed={inspectorCollapsed ? "true" : "false"}
          >
            <main id="main" className="app-main" tabIndex={-1}>
              <div hidden={activity !== "chat"} className="app-main__panel app-main__panel--chat">
                <ChatPage
                  chatClient={chat}
                  repositoryId={workspaceId}
                  historyOpen={historyOpen}
                  newChatRequest={newChatRequest}
                  orchestratorName={orchestratorName}
                  indexClient={index}
                  modelsClient={models}
                  onOpenWorkspace={() => {
                    go({ activity: "workspaces" });
                  }}
                  onOpenModels={() => {
                    go({ activity: "settings", settingsSection: "models" });
                  }}
                  onOpenGoals={() => {
                    go({ activity: "goals" });
                  }}
                  onApplyFile={
                    workspaceId
                      ? async (path, content) => {
                          await repos.writeFile(workspaceId, path, content);
                        }
                      : undefined
                  }
                  onOpenPath={() => {
                    go({ activity: "files" });
                  }}
                />
              </div>
              <div hidden={activity !== "files"} className="app-main__panel">
                <FilesPlaceholder />
              </div>
              {activity === "goals" ? (
                <div className="app-main__panel">
                  <GoalsPage engineClient={engine} goalsClient={goalsPageClient} />
                  <RunsPage engineClient={engine} />
                </div>
              ) : null}
              {activity === "workspaces" ? (
                <div className="app-main__panel">
                  <WorkspacesPage
                    engineClient={engine}
                    repositoriesClient={repos}
                    pickFolder={pickRepositoryFolder}
                  />
                </div>
              ) : null}
              {activity === "settings" ? (
                <div className="app-main__panel app-main__panel--settings">
                  <SettingsHub
                    engineClient={engine}
                    section={route.settingsSection}
                    onSection={(section: SettingsSection) => {
                      go({ activity: "settings", settingsSection: section });
                    }}
                    modelsClient={models}
                    settingsClient={settings}
                  />
                </div>
              ) : null}
            </main>
            {inspectorCollapsed ? null : (
              <InspectorDrawer
                tab={inspectorTab}
                onTab={setInspectorTab}
                changes={session.changes}
                goals={session.goals}
                checks={session.checks}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function FilesPlaceholder() {
  return (
    <section>
      <p className="page-kicker">Files</p>
      <h1 className="page-title">Files</h1>
      <p className="page-body">
        The editor arrives later. Open a git folder from Workspaces to browse files here.
      </p>
    </section>
  );
}
