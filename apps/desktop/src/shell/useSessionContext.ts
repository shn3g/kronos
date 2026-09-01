// SPDX-License-Identifier: AGPL-3.0-or-later

import { useEffect, useRef, useState } from "react";
import type { GoalRecord, GoalsClient } from "../features/goals/client";
import { checksFromLocal, type HealthCheck } from "../features/health/checks";
import type { HomeClient, HomeDashboard } from "../features/home/client";
import type { SettingsPageClients } from "../features/settings/client";
import type { EnrolledRepository, RepositoriesClient } from "../features/workspaces/client";
import type { InspectorChange } from "./InspectorDrawer";
import { inspectWorkspaceChanges } from "./inspectWorkspaceChanges";
import {
  readStoredWorkspaceId,
  resolveActiveWorkspaceId,
  writeStoredWorkspaceId,
} from "./resolveWorkspace";

interface SessionContextInput {
  engineReady: boolean;
  modelReady: boolean;
  repositoriesClient: RepositoriesClient;
  homeClient: HomeClient;
  goalsClient: GoalsClient;
  settingsClient: SettingsPageClients;
}

function changesForWorkspace(dashboard: HomeDashboard, workspaceId: string | null): InspectorChange[] {
  return inspectWorkspaceChanges(dashboard.diffs, workspaceId);
}

function goalsForWorkspace(
  listed: GoalRecord[],
  workspaceId: string | null,
): { id: string; title: string; state: string }[] {
  return listed
    .filter((item) => !workspaceId || item.repositoryId === workspaceId)
    .map((item) => ({ id: item.id, title: item.title, state: item.state }));
}

function indexReadyForWorkspace(dashboard: HomeDashboard, workspaceId: string | null): boolean {
  if (!workspaceId) {
    return false;
  }
  return dashboard.index.some((item) => item.repositoryId === workspaceId && item.ready);
}

export function useSessionContext({
  engineReady,
  modelReady,
  repositoriesClient,
  homeClient,
  goalsClient,
  settingsClient,
}: SessionContextInput): {
  repositories: EnrolledRepository[];
  workspaceId: string | null;
  setWorkspaceId: (id: string | null) => void;
  changes: InspectorChange[];
  goals: { id: string; title: string; state: string }[];
  checks: HealthCheck[];
  refresh: () => Promise<void>;
} {
  const [repositories, setRepositories] = useState<EnrolledRepository[]>([]);
  const [workspaceId, setWorkspaceIdState] = useState<string | null>(null);
  const [changes, setChanges] = useState<InspectorChange[]>([]);
  const [goals, setGoals] = useState<{ id: string; title: string; state: string }[]>([]);
  const [doctorChecks, setDoctorChecks] = useState<HealthCheck[] | null>(null);
  const [indexReady, setIndexReady] = useState(false);
  const dashboardRef = useRef<HomeDashboard | null>(null);
  const goalsRef = useRef<GoalRecord[]>([]);
  const refreshRef = useRef<() => Promise<void>>(async () => undefined);

  function applyWorkspace(id: string | null): void {
    setWorkspaceIdState(id);
    const dashboard = dashboardRef.current;
    if (dashboard) {
      setChanges(changesForWorkspace(dashboard, id));
      setIndexReady(indexReadyForWorkspace(dashboard, id));
    }
    setGoals(goalsForWorkspace(goalsRef.current, id));
  }

  function setWorkspaceId(id: string | null): void {
    writeStoredWorkspaceId(id);
    applyWorkspace(id);
  }

  useEffect(() => {
    if (!engineReady) {
      return;
    }
    let cancelled = false;
    const refresh = async () => {
      let listedRepos: EnrolledRepository[] = [];
      try {
        listedRepos = await repositoriesClient.list();
        if (cancelled) {
          return;
        }
        setRepositories(listedRepos);
      } catch {
        if (cancelled) {
          return;
        }
        listedRepos = [];
        setRepositories([]);
      }
      try {
        const dashboard = await homeClient.dashboard();
        if (!cancelled) {
          dashboardRef.current = dashboard;
        }
      } catch {
        if (!cancelled) {
          dashboardRef.current = null;
          setChanges([]);
          setIndexReady(false);
        }
      }
      try {
        const listed = await goalsClient.list();
        if (!cancelled) {
          goalsRef.current = listed;
        }
      } catch {
        if (!cancelled) {
          goalsRef.current = [];
          setGoals([]);
        }
      }
      try {
        const doctor = await settingsClient.doctor();
        if (!cancelled && doctor.checks.length > 0) {
          setDoctorChecks(doctor.checks);
        }
      } catch {
        if (!cancelled) {
          setDoctorChecks(null);
        }
      }
      if (cancelled) {
        return;
      }
      applyWorkspace(resolveActiveWorkspaceId(listedRepos, readStoredWorkspaceId()));
    };
    refreshRef.current = refresh;
    void refresh();
    const interval = window.setInterval(() => {
      void refresh();
    }, 2500);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [engineReady, repositoriesClient, homeClient, goalsClient, settingsClient]);

  const localChecks = checksFromLocal({
    engineReady,
    modelReady,
    workspaceReady: Boolean(workspaceId),
    indexReady: Boolean(workspaceId) && indexReady,
  });

  return {
    repositories,
    workspaceId,
    setWorkspaceId,
    changes,
    goals,
    checks: doctorChecks ?? localChecks,
    refresh: () => refreshRef.current(),
  };
}
