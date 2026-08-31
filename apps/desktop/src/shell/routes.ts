// SPDX-License-Identifier: AGPL-3.0-or-later

export const ROUTES = [
  {
    path: "/",
    name: "Home",
    heading: "Home",
    summary:
      "Kronos is a local software-engineering operating system. Goals, runs, and repository work appear here once an engine is connected.",
  },
  {
    path: "/workspaces",
    name: "Workspaces",
    heading: "Workspaces",
    summary: "Enrolled repositories will list here with isolated indexes and policy.",
  },
  {
    path: "/goals",
    name: "Goals",
    heading: "Goals",
    summary: "Bounded goals are planned and tracked from this screen.",
  },
  {
    path: "/runs",
    name: "Runs",
    heading: "Runs",
    summary: "Task runs, tests, and review evidence stream here.",
  },
  {
    path: "/skills",
    name: "Skills",
    heading: "Skills",
    summary: "Browse curated skills, quarantine imports, and approve activation.",
  },
  {
    path: "/memory",
    name: "Memory",
    heading: "Memory",
    summary: "Inspect episodic and procedural records. Imported lessons stay disabled.",
  },
  {
    path: "/models",
    name: "Models",
    heading: "Models",
    summary: "Assign planner, coder, reviewer, and embedding profiles. Fail closed without an engine.",
  },
  {
    path: "/index",
    name: "Index",
    heading: "Index",
    summary: "Per-repository hybrid index status and fail-closed search.",
  },
  {
    path: "/connections",
    name: "Connections",
    heading: "Connections",
    summary: "Create and install GitHub Apps and connect Telegram. Fail closed without an engine.",
  },
  {
    path: "/settings",
    name: "Settings",
    heading: "Settings",
    summary: "Doctor, backup, and export toggles. Secrets never pass through the WebView.",
  },
  {
    path: "/updates",
    name: "Updates",
    heading: "Updates",
    summary: "Version, checksums, SBOM, and rollback. Unsigned when signing keys are absent.",
  },
  {
    path: "/notifications",
    name: "Notifications",
    heading: "Notifications",
    summary: "Paused work and degraded indexes. Fail closed without an engine.",
  },
] as const;

export type RoutePath = (typeof ROUTES)[number]["path"];

export function pathFromHash(hash: string): string {
  const raw = hash.replace(/^#/, "");
  const path = raw.startsWith("/") ? raw : `/${raw}`;
  const normalized = path === "/" ? "/" : path.replace(/\/+$/, "");
  return ROUTES.some((route) => route.path === normalized) ? normalized : "/";
}
