// SPDX-License-Identifier: AGPL-3.0-or-later

import type { ModelsSnapshot } from "./client";

export function plannerDisplayName(snapshot: ModelsSnapshot): string | null {
  const plannerId = snapshot.assignments.planner;
  if (!plannerId) {
    return null;
  }
  const profile = snapshot.profiles.find((item) => item.id === plannerId);
  return profile?.displayName ?? null;
}
