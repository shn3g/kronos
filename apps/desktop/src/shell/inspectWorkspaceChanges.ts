// SPDX-License-Identifier: AGPL-3.0-or-later

import type { InspectorChange } from "./InspectorDrawer";

export interface WorkspaceDiff {
  path: string;
  summary: string;
  patch?: string;
  repositoryId?: string;
}

export function inspectWorkspaceChanges(
  diffs: WorkspaceDiff[],
  workspaceId: string | null,
): InspectorChange[] {
  const matched = diffs.filter(
    (item) => !workspaceId || !item.repositoryId || item.repositoryId === workspaceId,
  );
  const seen = new Set<string>();
  const changes: InspectorChange[] = [];
  for (let index = matched.length - 1; index >= 0; index -= 1) {
    const item = matched[index];
    if (!item || seen.has(item.path)) {
      continue;
    }
    seen.add(item.path);
    changes.push({ path: item.path, summary: item.summary, patch: item.patch ?? "" });
  }
  return changes;
}

export type ChangeListScope = "turn" | "all";

export function visibleInspectorChanges(
  changes: InspectorChange[],
  scope: ChangeListScope,
): InspectorChange[] {
  if (scope === "all") {
    return changes;
  }
  return changes.filter((item) => item.fromChat === true);
}
