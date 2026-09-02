// SPDX-License-Identifier: AGPL-3.0-or-later

import type { EnrolledRepository } from "../features/workspaces/client";

export const ACTIVE_WORKSPACE_STORAGE_KEY = "kronos.activeWorkspaceId";

export function resolveActiveWorkspaceId(
  repositories: EnrolledRepository[],
  stored: string | null,
): string | null {
  const active = repositories.filter((item) => item.status === "active");
  if (stored === "") {
    return null;
  }
  if (stored && active.some((item) => item.id === stored)) {
    return stored;
  }
  return active[0]?.id ?? null;
}

export function readStoredWorkspaceId(): string | null {
  if (typeof window === "undefined" || typeof window.localStorage === "undefined") {
    return null;
  }
  return window.localStorage.getItem(ACTIVE_WORKSPACE_STORAGE_KEY);
}

export function writeStoredWorkspaceId(id: string | null): void {
  if (typeof window === "undefined" || typeof window.localStorage === "undefined") {
    return;
  }
  window.localStorage.setItem(ACTIVE_WORKSPACE_STORAGE_KEY, id ?? "");
}
