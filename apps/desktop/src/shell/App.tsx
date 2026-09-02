// SPDX-License-Identifier: AGPL-3.0-or-later

import { useEffect, useState } from "react";
import {
  createProductionEngineClient,
  type EngineClient,
  type EngineConnectionState,
} from "../engine/client";
import { EngineStatus } from "../engine/EngineStatus";
import { ChatPage, type ChatMentionRequest } from "../features/chat/ChatPage";
import { createProductionChatClient, type ChatClient } from "../features/chat/client";
import { FilesPage } from "../features/files/FilesPage";
import { GoToFilePalette } from "../features/files/GoToFilePalette";
import {
  ASK_IN_CHAT_EVENT,
  FIND_IN_FILE_EVENT,
  FIND_IN_FILES_EVENT,
  GO_TO_LINE_EVENT,
  REPLACE_IN_FILE_EVENT,
} from "../features/files/fileEditor";
import { safeWorkspaceRelPath } from "../features/files/workspacePath";
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
  const [mentionRequest, setMentionRequest] = useState<ChatMentionRequest>({
    path: "",
    nonce: 0,
    selectedText: "",
    startLine: 0,
    endLine: 0,
  });
  const [fileReveal, setFileReveal] = useState({ path: "", nonce: 0 });
  const [goToFileOpen, setGoToFileOpen] = useState(false);
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
    setFileReveal({ path: "", nonce: 0 });
  }, [session.workspaceId]);

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

  function revealWorkspaceFile(path: string): void {
    const safe = safeWorkspaceRelPath(path);
    if (safe === "") {
      return;
    }
    setFileReveal((current) => ({ path: safe, nonce: current.nonce + 1 }));
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
      if (action === "toggle-terminal") {
        return;
      }
      if (action === "go-to-file") {
        event.preventDefault();
        setGoToFileOpen(true);
        return;
      }
      if (action === "find-in-files") {
        event.preventDefault();
        go({ activity: "files" });
        window.dispatchEvent(new Event(FIND_IN_FILES_EVENT));
        return;
      }
      if (action === "ask-in-chat") {
        event.preventDefault();
        window.dispatchEvent(new Event(ASK_IN_CHAT_EVENT));
        go({ activity: "chat" });
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
        onGoToFile={() => {
          setGoToFileOpen(true);
        }}
        onFindInFile={() => {
          go({ activity: "files" });
          window.dispatchEvent(new Event(FIND_IN_FILE_EVENT));
        }}
        onFindInFiles={() => {
          go({ activity: "files" });
          window.dispatchEvent(new Event(FIND_IN_FILES_EVENT));
        }}
        onReplaceInFile={() => {
          go({ activity: "files" });
          window.dispatchEvent(new Event(REPLACE_IN_FILE_EVENT));
        }}
        onGoToLine={() => {
          go({ activity: "files" });
          window.dispatchEvent(new Event(GO_TO_LINE_EVENT));
        }}
        onAskInChat={() => {
          window.dispatchEvent(new Event(ASK_IN_CHAT_EVENT));
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
                  mentionRequest={mentionRequest}
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
                  onOpenPath={revealWorkspaceFile}
                />
              </div>
              <div hidden={activity !== "files"} className="app-main__panel app-main__panel--files">
                <FilesPage
                  engineClient={engine}
                  repositoryId={workspaceId}
                  repositoriesClient={repos}
                  indexClient={index}
                  onOpenWorkspace={() => {
                    go({ activity: "workspaces" });
                  }}
                  onAskInChat={(path, selection) => {
                    setMentionRequest((current) => ({
                      path,
                      nonce: current.nonce + 1,
                      selectedText: selection?.text ?? "",
                      startLine: selection?.startLine ?? 0,
                      endLine: selection?.endLine ?? 0,
                    }));
                    go({ activity: "chat" });
                  }}
                  onWroteFile={() => {
                    void session.refresh();
                  }}
                  revealRequest={fileReveal}
                />
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
                onOpenPath={revealWorkspaceFile}
              />
            )}
          </div>
        </div>
      </div>
      <GoToFilePalette
        open={goToFileOpen}
        repositoryId={workspaceId}
        repositoriesClient={repos}
        onClose={() => {
          setGoToFileOpen(false);
        }}
        onOpenWorkspace={() => {
          go({ activity: "workspaces" });
        }}
        onSelect={revealWorkspaceFile}
      />
    </div>
  );
}
