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
    summary: "Bounded goals will be planned and tracked from this screen.",
  },
  {
    path: "/runs",
    name: "Runs",
    heading: "Runs",
    summary: "Task runs, tests, and review evidence will stream here.",
  },
  {
    path: "/skills",
    name: "Skills",
    heading: "Skills",
    summary: "Curated engineering skills will be browsed and activated here.",
  },
  {
    path: "/models",
    name: "Models",
    heading: "Models",
    summary: "Planner, coder, reviewer, and embedding profiles will be assigned here.",
  },
  {
    path: "/connections",
    name: "Connections",
    heading: "Connections",
    summary: "GitHub, Telegram, and local tool connections will be configured here.",
  },
] as const;

export type RoutePath = (typeof ROUTES)[number]["path"];

export function pathFromHash(hash: string): string {
  const raw = hash.replace(/^#/, "");
  const path = raw.startsWith("/") ? raw : `/${raw}`;
  const normalized = path === "/" ? "/" : path.replace(/\/+$/, "");
  return ROUTES.some((route) => route.path === normalized) ? normalized : "/";
}
