// SPDX-License-Identifier: AGPL-3.0-or-later

/** Map a failed goal-readiness check id to the hash route that fixes it. */
export function readinessFixHref(checkId: string): string | null {
  switch (checkId) {
    case "workspace_active":
    case "mode_allows_writes":
      return "#/workspaces";
    case "models_assigned":
      return "#/settings/models";
    case "github_controller":
    case "reviewer_app":
    case "ruleset_strict":
    case "kronos_pr_workflow":
    case "codeowners":
      return "#/settings/connections";
    case "budget":
      return null;
    default:
      return null;
  }
}
