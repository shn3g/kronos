// SPDX-License-Identifier: AGPL-3.0-or-later

export type SettingsSection =
  | "general"
  | "models"
  | "index"
  | "connections"
  | "skills"
  | "memory"
  | "updates"
  | "notifications";

export type ShellActivity = "chat" | "files" | "goals" | "workspaces" | "settings";

export interface ShellRoute {
  activity: ShellActivity;
  settingsSection: SettingsSection;
}

export const SETTINGS_SECTIONS: { id: SettingsSection; label: string }[] = [
  { id: "general", label: "General" },
  { id: "models", label: "Models" },
  { id: "index", label: "Index" },
  { id: "connections", label: "Connections" },
  { id: "skills", label: "Skills" },
  { id: "memory", label: "Memory" },
  { id: "updates", label: "Updates" },
  { id: "notifications", label: "Notifications" },
];

const SETTINGS_IDS = new Set<string>(SETTINGS_SECTIONS.map((item) => item.id));

const ACTIVITIES = new Set<ShellActivity>(["chat", "files", "goals", "workspaces", "settings"]);

const LEGACY_PATHS: Record<string, ShellRoute> = {
  "/": { activity: "chat", settingsSection: "general" },
  "/models": { activity: "settings", settingsSection: "models" },
  "/index": { activity: "settings", settingsSection: "index" },
  "/connections": { activity: "settings", settingsSection: "connections" },
  "/skills": { activity: "settings", settingsSection: "skills" },
  "/memory": { activity: "settings", settingsSection: "memory" },
  "/updates": { activity: "settings", settingsSection: "updates" },
  "/notifications": { activity: "settings", settingsSection: "notifications" },
  "/runs": { activity: "goals", settingsSection: "general" },
};

function normalizeHash(hash: string): string {
  const raw = hash.replace(/^#/, "");
  const path = raw.startsWith("/") ? raw : `/${raw}`;
  if (path === "/" || path === "") {
    return "/";
  }
  return path.replace(/\/+$/, "");
}

function isSettingsSection(value: string): value is SettingsSection {
  return SETTINGS_IDS.has(value);
}

function isActivity(value: string): value is ShellActivity {
  return ACTIVITIES.has(value as ShellActivity);
}

export function routeFromHash(hash: string): ShellRoute {
  const path = normalizeHash(hash);
  if (path === "/settings") {
    return { activity: "settings", settingsSection: "general" };
  }
  const settingsMatch = /^\/settings\/([^/]+)$/.exec(path);
  if (settingsMatch && isSettingsSection(settingsMatch[1] ?? "")) {
    return { activity: "settings", settingsSection: settingsMatch[1] as SettingsSection };
  }
  if (path.length > 1) {
    const activity = path.slice(1);
    if (isActivity(activity) && activity !== "settings") {
      return { activity, settingsSection: "general" };
    }
  }
  return LEGACY_PATHS[path] ?? { activity: "chat", settingsSection: "general" };
}

export function hashFromRoute(route: ShellRoute): string {
  if (route.activity === "settings") {
    if (route.settingsSection === "general") {
      return "#/settings";
    }
    return `#/settings/${route.settingsSection}`;
  }
  return `#/${route.activity}`;
}

