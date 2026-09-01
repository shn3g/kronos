// SPDX-License-Identifier: AGPL-3.0-or-later

import { useEffect, useState } from "react";
import {
  createProductionEngineClient,
  type EngineClient,
  type EngineConnectionState,
} from "../engine/client";
import { EngineStatus } from "../engine/EngineStatus";
import { WorkspacesPage } from "../features/workspaces/WorkspacesPage";
import {
  createProductionRepositoriesClient,
  pickRepositoryFolder,
  type RepositoriesClient,
} from "../features/workspaces/client";
import { ModelsPage } from "../features/models/ModelsPage";
import {
  createProductionModelsClient,
  type ModelsClient,
} from "../features/models/client";
import { IndexPage } from "../features/index/IndexPage";
import { SettingsPage } from "../features/settings/SettingsPage";
import {
  createProductionSettingsClient,
  type SettingsPageClients,
} from "../features/settings/client";
import { ChatPage } from "../features/chat/ChatPage";
import { createProductionChatClient, type ChatClient } from "../features/chat/client";
import { createProductionHomeClient, type HomeClient } from "../features/home/client";
import { createProductionGoalsClient, type GoalsClient } from "../features/goals/client";
import { MemoryPage } from "../features/memory/MemoryPage";
import { ActivityBar, type ActivityId } from "./ActivityBar";
import { ConnectModelGate } from "./ConnectModelGate";
import { CheckingModelGate, EngineGate } from "./EngineGate";
import { InspectorDrawer, type InspectorTab } from "./InspectorDrawer";
import { MenuBar } from "./MenuBar";
import { shellShortcutFromKeyboard } from "./shellShortcut";
import { useSessionContext } from "./useSessionContext";
import { WorkspaceSwitcher } from "./WorkspaceSwitcher";

const productionEngine = createProductionEngineClient();
const productionModels = createProductionModelsClient();
const productionChat = createProductionChatClient();
const productionRepos = createProductionRepositoriesClient();
const productionHome = createProductionHomeClient();
const productionGoals = createProductionGoalsClient();
const productionSettings = createProductionSettingsClient();
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
}

export function App({
  engineClient,
  modelsClient,
  chatClient,
  repositoriesClient,
  homeClient,
  goalsClient,
  settingsClient,
}: AppProps) {
  const engine = engineClient ?? productionEngine;
  const models = modelsClient ?? productionModels;
  const chat = chatClient ?? productionChat;
  const repos = repositoriesClient ?? productionRepos;
  const home = homeClient ?? productionHome;
  const goals = goalsClient ?? productionGoals;
  const settings = settingsClient ?? productionSettings;
  const [engineState, setEngineState] = useState<EngineConnectionState>({
    status: "starting",
  });
  const [modelReady, setModelReady] = useState(false);
  const [modelKnown, setModelKnown] = useState(false);
  const [activity, setActivity] = useState<ActivityId>("chat");
  const [historyOpen, setHistoryOpen] = useState(false);
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>("changes");
  const [newChatRequest, setNewChatRequest] = useState(0);
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
      setModelReady(Boolean(snapshot.assignments.planner));
      setModelKnown(true);
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
    settingsClient: settings,
  });

  function startNewChat(): void {
    setActivity("chat");
    setNewChatRequest((current) => current + 1);
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
    const onKey = (event: KeyboardEvent) => {
      const action = shellShortcutFromKeyboard(event);
      if (!action) {
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
      setActivity("settings");
    };
    window.addEventListener("keydown", onKey, true);
    return () => {
      window.removeEventListener("keydown", onKey, true);
    };
  }, [engineReady, modelKnown, modelReady]);

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
          setActivity("workspaces");
        }}
        onToggleHistory={() => {
          setHistoryOpen((open) => !open);
        }}
        onToggleActivityBar={toggleActivityBar}
        onToggleInspector={toggleInspector}
        onOpenSettings={() => {
          setActivity("settings");
        }}
        onOpenModels={() => {
          setActivity("settings");
        }}
      />
      <div className="app-body" data-rail-collapsed={activityCollapsed ? "true" : "false"}>
        <ActivityBar active={activity} collapsed={activityCollapsed} onSelect={setActivity} />
        <div className="app-stage">
          <header className="title-bar">
            <WorkspaceSwitcher
              repositories={session.repositories}
              workspaceId={session.workspaceId}
              onChange={session.setWorkspaceId}
              onOpenFolder={() => {
                setActivity("workspaces");
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
                  repositoryId={session.workspaceId}
                  historyOpen={historyOpen}
                  newChatRequest={newChatRequest}
                  onOpenWorkspace={() => {
                    setActivity("workspaces");
                  }}
                />
              </div>
              {activity === "workspaces" ? (
                <div className="app-main__panel">
                  <WorkspacesPage
                    engineClient={engine}
                    repositoriesClient={repos}
                    pickFolder={pickRepositoryFolder}
                  />
                </div>
              ) : null}
              {activity === "index" ? (
                <div className="app-main__panel">
                  <IndexPage engineClient={engine} />
                </div>
              ) : null}
              {activity === "settings" ? (
                <div className="app-main__panel app-main__panel--settings">
                  <SettingsPage engineClient={engine} settingsClient={settings} />
                  <MemoryPage engineClient={engine} headingLevel="h2" />
                  <ModelsPage engineClient={engine} modelsClient={models} headingLevel="h2" />
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
