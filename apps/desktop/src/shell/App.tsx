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
import { EngineGate } from "./EngineGate";
import { InspectorDrawer, type InspectorTab } from "./InspectorDrawer";
import { MenuBar } from "./MenuBar";
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
    status: "unavailable",
  });
  const [modelReady, setModelReady] = useState(false);
  const [modelKnown, setModelKnown] = useState(false);
  const [activity, setActivity] = useState<ActivityId>("chat");
  const [historyOpen, setHistoryOpen] = useState(false);
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>("changes");
  const [newChatRequest, setNewChatRequest] = useState(0);
  const [activityCollapsed, setActivityCollapsed] = useState(() => {
    if (typeof window === "undefined" || typeof window.localStorage === "undefined") {
      return false;
    }
    return window.localStorage.getItem(ACTIVITY_BAR_STORAGE_KEY) === "1";
  });

  useEffect(() => {
    let cancelled = false;
    const apply = () => {
      void engine.getState().then((next) => {
        if (!cancelled) {
          setEngineState(next);
        }
      });
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
      setModelKnown(engineState.status !== "starting");
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

  if (engineState.status !== "ready") {
    return (
      <div className="app-shell app-shell--gate">
        <a className="skip-link" href="#main">
          Skip to main content
        </a>
        <EngineStatus client={engine} />
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
        <EngineStatus client={engine} />
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
        <EngineStatus client={engine} />
        <main id="main">
          <EngineGate starting />
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
        onNewChat={() => {
          setActivity("chat");
          setNewChatRequest((current) => current + 1);
        }}
        onOpenWorkspace={() => {
          setActivity("workspaces");
        }}
        onToggleHistory={() => {
          setHistoryOpen((open) => !open);
        }}
        onToggleActivityBar={() => {
          setActivityCollapsed((current) => {
            const next = !current;
            window.localStorage.setItem(ACTIVITY_BAR_STORAGE_KEY, next ? "1" : "0");
            return next;
          });
        }}
        onOpenSettings={() => {
          setActivity("settings");
        }}
        onOpenModels={() => {
          setActivity("settings");
        }}
      />
      <div className="app-body">
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
            <EngineStatus client={engine} />
          </header>
          <div className="app-columns">
            <main id="main" className="app-main" tabIndex={-1}>
              <div hidden={activity !== "chat"}>
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
                <WorkspacesPage
                  engineClient={engine}
                  repositoriesClient={repos}
                  pickFolder={pickRepositoryFolder}
                />
              ) : null}
              {activity === "index" ? <IndexPage engineClient={engine} /> : null}
              {activity === "settings" ? (
                <>
                  <SettingsPage engineClient={engine} settingsClient={settings} />
                  <MemoryPage engineClient={engine} />
                  <ModelsPage engineClient={engine} modelsClient={models} />
                </>
              ) : null}
            </main>
            <InspectorDrawer
              tab={inspectorTab}
              onTab={setInspectorTab}
              changes={session.changes}
              goals={session.goals}
              checks={session.checks}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
