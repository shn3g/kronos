// SPDX-License-Identifier: AGPL-3.0-or-later

import { useEffect, useRef, useState } from "react";
import {
  createProductionEngineClient,
  type EngineClient,
} from "../engine/client";
import {
  EngineConnectionProvider,
  useEngineConnection,
} from "../engine/EngineConnectionProvider";
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
import { GoalsWorkbench, type GoalsWorkbenchClients } from "../features/goals/GoalsWorkbench";
import { createProductionGoalsClient, type GoalsClient } from "../features/goals/client";
import { createProductionHomeClient, type HomeClient } from "../features/home/client";
import { createProductionModelsClient, type ModelsClient } from "../features/models/client";
import { createProductionNotificationsClient, type NotificationsPageClients } from "../features/notifications/client";
import { createProductionRunsClient } from "../features/runs/client";
import { TerminalPage } from "../features/terminal/TerminalPage";
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
import { EmbeddingsGate } from "./EmbeddingsGate";
import { InspectorDrawer, type InspectorTab } from "./InspectorDrawer";
import { MenuBar } from "./MenuBar";
import { openRepositoryFolder } from "./openFolder";
import { hashFromRoute, routeFromHash, type SettingsSection, type ShellRoute } from "./routes";
import { shellShortcutFromKeyboard } from "./shellShortcut";
import { useSessionContext } from "./useSessionContext";
import { setDesktopWindowTitle } from "./windowTitle";
import { WorkspaceGate } from "./WorkspaceGate";
import { WorkspaceSwitcher } from "./WorkspaceSwitcher";

const productionEngine = createProductionEngineClient();
const productionModels = createProductionModelsClient();
const productionChat = createProductionChatClient();
const productionRepos = createProductionRepositoriesClient();
const productionHome = createProductionHomeClient();
const productionGoals = createProductionGoalsClient();
const productionRuns = createProductionRunsClient();
const productionSettings = createProductionSettingsClient();
const productionIndex = createProductionIndexClient();
const productionNotifications = createProductionNotificationsClient();
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
  notificationsClient?: NotificationsPageClients;
}

export function App(props: AppProps) {
  const engine = props.engineClient ?? productionEngine;
  return (
    <EngineConnectionProvider engineClient={engine}>
      <AppShell {...props} />
    </EngineConnectionProvider>
  );
}

function AppShell({
  modelsClient,
  chatClient,
  repositoriesClient,
  homeClient,
  goalsClient,
  settingsClient,
  indexClient,
  notificationsClient,
}: AppProps) {
  const models = modelsClient ?? productionModels;
  const chat = chatClient ?? productionChat;
  const repos = repositoriesClient ?? productionRepos;
  const home = homeClient ?? productionHome;
  const goals = goalsClient ?? productionGoals;
  const settings = settingsClient ?? productionSettings;
  const index = indexClient ?? productionIndex;
  const notifications = notificationsClient ?? productionNotifications;
  const { state: engineState, engineReady } = useEngineConnection();
  const [modelReady, setModelReady] = useState(false);
  const [modelKnown, setModelKnown] = useState(false);
  const [embeddingsReady, setEmbeddingsReady] = useState(false);
  const [embeddingsKnown, setEmbeddingsKnown] = useState(false);
  const [firstRun, setFirstRun] = useState(false);
  const [workspaceStepDone, setWorkspaceStepDone] = useState(false);
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
  const [goalReveal, setGoalReveal] = useState({ id: "", nonce: 0 });
  const [goToFileOpen, setGoToFileOpen] = useState(false);
  const [orchestratorName, setOrchestratorName] = useState<string | null>(null);
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>("changes");
  const [activityCollapsed, setActivityCollapsed] = useState(() =>
    readFlag(ACTIVITY_BAR_STORAGE_KEY),
  );
  const [inspectorCollapsed, setInspectorCollapsed] = useState(() =>
    readFlag(INSPECTOR_STORAGE_KEY),
  );
  const [terminalOpen, setTerminalOpen] = useState(false);
  const [revertError, setRevertError] = useState<string | null>(null);
  const [revertingPath, setRevertingPath] = useState<string | null>(null);
  const revertingRef = useRef(false);
  const [commitError, setCommitError] = useState<string | null>(null);
  const [committing, setCommitting] = useState(false);
  const committingRef = useRef(false);
  const [notificationCount, setNotificationCount] = useState(0);
  const [folderError, setFolderError] = useState<string | null>(null);

  useEffect(() => {
    if (!engineReady) {
      // Keep prior model/embedding readiness across brief respawn blips so the
      // shell does not bounce through "Checking the model connection" again.
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

  useEffect(() => {
    if (!engineReady) {
      return;
    }
    if (!modelReady) {
      setEmbeddingsReady(false);
      setEmbeddingsKnown(false);
      return;
    }
    let cancelled = false;
    void models.embeddingInstall().then(
      (snapshot) => {
        if (cancelled) {
          return;
        }
        const installed =
          snapshot.activeKey !== null || snapshot.catalog.some((item) => item.installed);
        setEmbeddingsKnown(true);
        if (installed) {
          setEmbeddingsReady(true);
        }
      },
      () => {
        if (!cancelled) {
          setEmbeddingsKnown(true);
        }
      },
    );
    return () => {
      cancelled = true;
    };
  }, [engineReady, modelReady, models]);

  const session = useSessionContext({
    engineReady,
    modelReady,
    repositoriesClient: repos,
    homeClient: home,
    goalsClient: goals,
    settingsClient: settings,
  });

  const workspaceStepOpen =
    firstRun && !workspaceStepDone && session.repositories.length === 0;
  const shellReady =
    engineReady &&
    modelKnown &&
    modelReady &&
    embeddingsKnown &&
    embeddingsReady &&
    !workspaceStepOpen;

  async function revertChange(path: string): Promise<void> {
    if (!session.workspaceId || revertingRef.current) {
      return;
    }
    revertingRef.current = true;
    setRevertError(null);
    setCommitError(null);
    setRevertingPath(path);
    try {
      await repos.revertWrite(session.workspaceId, path);
      await session.refresh();
    } catch {
      setRevertError("Could not revert that file. Check the workspace and try again.");
    } finally {
      revertingRef.current = false;
      setRevertingPath(null);
    }
  }

  async function commitChanges(message: string, paths: string[]): Promise<void> {
    if (!session.workspaceId || committingRef.current || paths.length === 0) {
      return;
    }
    committingRef.current = true;
    setCommitting(true);
    setCommitError(null);
    setRevertError(null);
    try {
      await repos.commitFiles(session.workspaceId, message, paths);
      await session.refresh();
    } catch {
      setCommitError("Could not commit those files. Check the message and try again.");
    } finally {
      committingRef.current = false;
      setCommitting(false);
    }
  }

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

  function toggleTerminal(): void {
    setTerminalOpen((open) => !open);
  }

  async function handleOpenFolder(): Promise<void> {
    setFolderError(null);
    try {
      const result = await openRepositoryFolder(repos, {
        repositories: session.repositories,
      });
      if (!result) {
        return;
      }
      session.setWorkspaceId(result.repository.id);
      await session.refresh();
      setWorkspaceStepDone(true);
      go({ activity: "files" });
    } catch (error) {
      setFolderError(error instanceof Error ? error.message : "Could not open that folder.");
    }
  }

  function onFolderOpened(repository: { id: string }): void {
    session.setWorkspaceId(repository.id);
    void session.refresh();
    setWorkspaceStepDone(true);
    go({ activity: "files" });
  }

  useEffect(() => {
    if (!shellReady) {
      return;
    }
    const expected = hashFromRoute(route);
    if (window.location.hash !== expected) {
      window.location.hash = expected;
    }
  }, [shellReady, route]);

  useEffect(() => {
    if (!shellReady) {
      setNotificationCount(0);
      return;
    }
    let cancelled = false;
    const apply = () => {
      void notifications.list().then(
        (items) => {
          if (!cancelled) {
            setNotificationCount(items.length);
          }
        },
        () => {
          if (!cancelled) {
            setNotificationCount(0);
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
  }, [shellReady, notifications]);

  useEffect(() => {
    if (!shellReady) {
      return;
    }
    const onKey = (event: KeyboardEvent) => {
      const action = shellShortcutFromKeyboard(event);
      if (!action) {
        return;
      }
      if (action === "toggle-terminal") {
        event.preventDefault();
        toggleTerminal();
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
  }, [shellReady, route]);

  useEffect(() => {
    if (!shellReady) {
      return;
    }
    const repo = session.repositories.find((item) => item.id === session.workspaceId);
    const title = repo ? `Kronos — ${repo.displayName}` : "Kronos";
    void setDesktopWindowTitle(title);
  }, [shellReady, session.repositories, session.workspaceId]);

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

  if (!modelKnown) {
    return (
      <div className="app-shell app-shell--gate">
        <a className="skip-link" href="#main">
          Skip to main content
        </a>
        <EngineStatus state={engineState} />
        <main id="main" tabIndex={-1}>
          <CheckingModelGate />
        </main>
      </div>
    );
  }

  if (!modelReady) {
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
              setFirstRun(true);
            }}
          />
        </main>
      </div>
    );
  }

  if (!embeddingsKnown) {
    return (
      <div className="app-shell app-shell--gate">
        <a className="skip-link" href="#main">
          Skip to main content
        </a>
        <EngineStatus state={engineState} />
        <main id="main" tabIndex={-1}>
          <CheckingModelGate label="Checking local embeddings" />
        </main>
      </div>
    );
  }

  if (!embeddingsReady) {
    return (
      <div className="app-shell app-shell--gate">
        <a className="skip-link" href="#main">
          Skip to main content
        </a>
        <EngineStatus state={engineState} />
        <main id="main" tabIndex={-1}>
          <EmbeddingsGate
            modelsClient={models}
            onReady={() => {
              setEmbeddingsReady(true);
            }}
          />
        </main>
      </div>
    );
  }

  if (workspaceStepOpen) {
    return (
      <div className="app-shell app-shell--gate">
        <a className="skip-link" href="#main">
          Skip to main content
        </a>
        <EngineStatus state={engineState} />
        <main id="main" tabIndex={-1}>
          <WorkspaceGate
            onOpenWorkspace={() => {
              void handleOpenFolder();
            }}
            onSkip={() => {
              setWorkspaceStepDone(true);
              go({ activity: "chat" });
            }}
          />
        </main>
      </div>
    );
  }

  const activity: ActivityId = route.activity;
  const goalsPageClient: GoalsWorkbenchClients = {
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
        terminalOpen={terminalOpen}
        onNewChat={startNewChat}
        onOpenFolder={() => {
          void handleOpenFolder();
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
        onToggleTerminal={toggleTerminal}
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
          notificationCount={notificationCount}
          onSelect={(id) => {
            go({ activity: id });
          }}
        />
        <div className="app-stage">
          <header className="title-bar">
            <WorkspaceSwitcher
              repositories={session.repositories}
              workspaceId={session.workspaceId}
              indexReady={session.indexReady}
              onChange={session.setWorkspaceId}
              onOpenFolder={() => {
                void handleOpenFolder();
              }}
            />
            {folderError ? (
              <p className="title-bar__folder-error" role="alert">
                {folderError}
              </p>
            ) : null}
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
                    void handleOpenFolder();
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
                  repositoryId={workspaceId}
                  repositoriesClient={repos}
                  indexClient={index}
                  onOpenWorkspace={() => {
                    void handleOpenFolder();
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
                  <GoalsWorkbench
                    goalsClient={goalsPageClient}
                    repositoriesClient={repos}
                    runsClient={productionRuns}
                    selectedGoalReveal={goalReveal}
                  />
                </div>
              ) : null}
              {activity === "workspaces" ? (
                <div className="app-main__panel">
                  <WorkspacesPage
                    repositoriesClient={repos}
                    pickFolder={pickRepositoryFolder}
                    onFolderOpened={onFolderOpened}
                  />
                </div>
              ) : null}
              {activity === "settings" ? (
                <div className="app-main__panel app-main__panel--settings">
                  <SettingsHub
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
                onRevert={(path) => {
                  void revertChange(path);
                }}
                revertError={revertError}
                revertingPath={revertingPath}
                onCommit={(message, paths) => {
                  void commitChanges(message, paths);
                }}
                commitError={commitError}
                committing={committing}
                onOpenPath={revealWorkspaceFile}
                onOpenGoal={(goalId) => {
                  setGoalReveal((current) => ({ id: goalId, nonce: current.nonce + 1 }));
                  go({ activity: "goals" });
                }}
              />
            )}
          </div>
          <section
            className="app-terminal"
            id="terminal"
            hidden={!terminalOpen}
            aria-label="Terminal"
          >
            <TerminalPage
              repositoryId={workspaceId}
              repositoriesClient={repos}
              onOpenWorkspace={() => {
                void handleOpenFolder();
              }}
            />
          </section>
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
          void handleOpenFolder();
        }}
        onSelect={revealWorkspaceFile}
      />
    </div>
  );
}
