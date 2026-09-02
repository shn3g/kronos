// SPDX-License-Identifier: AGPL-3.0-or-later

export function safeWorkspaceRelPath(value: string): string {
  const trimmed = value.trim().replace(/\\/g, "/").replace(/^\/+/, "");
  if (trimmed === "") {
    return "";
  }
  const parts = trimmed.split("/");
  if (parts.some((part) => part === "" || part === "." || part === ".." || part === ".git")) {
    return "";
  }
  return parts.join("/");
}

export function ancestorFolderPaths(path: string): string[] {
  const safe = safeWorkspaceRelPath(path);
  if (safe === "") {
    return [];
  }
  const parts = safe.split("/");
  const folders: string[] = [];
  for (let index = 1; index < parts.length; index += 1) {
    folders.push(parts.slice(0, index).join("/"));
  }
  return folders;
}

export function looksLikeWorkspaceFilePath(value: string): boolean {
  const safe = safeWorkspaceRelPath(value);
  if (safe === "") {
    return false;
  }
  return safe.includes("/") || safe.includes(".");
}
