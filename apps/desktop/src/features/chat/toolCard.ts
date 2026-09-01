// SPDX-License-Identifier: AGPL-3.0-or-later

const TOOL_LABELS: Record<string, string> = {
  search_index: "Search index",
  read_file: "Read file",
  write_file: "Write file",
  search_memory: "Search memory",
  create_goal: "Create goal",
  list_goals: "List goals",
};

export function toolCardLabel(name: string | null, status: string | null): string {
  const label = (name && TOOL_LABELS[name]) || name || "Tool";
  if (status === "ok") {
    return `${label} · done`;
  }
  if (status === "error") {
    return `${label} · failed`;
  }
  if (status === "running") {
    return `${label} · running`;
  }
  return label;
}
