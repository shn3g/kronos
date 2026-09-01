// SPDX-License-Identifier: AGPL-3.0-or-later

import { safeWorkspaceRelPath } from "./workspacePath";

export const GO_TO_FILE_RESULT_LIMIT = 50;

export function rankWorkspaceFilePaths(
  paths: readonly string[],
  query: string,
  limit: number = GO_TO_FILE_RESULT_LIMIT,
): string[] {
  const unique = uniqueSafePaths(paths);
  const cap = Math.max(0, limit);
  const needle = query.trim().toLowerCase();
  if (needle === "") {
    return unique.slice(0, cap);
  }
  const scored = unique
    .map((path) => ({ path, score: filePathMatchScore(path, needle) }))
    .filter((item): item is { path: string; score: number } => item.score !== null);
  scored.sort(compareScoredPaths);
  return scored.slice(0, cap).map((item) => item.path);
}

export function nextGoToFileIndex(current: number, delta: number, length: number): number {
  if (length <= 0) {
    return 0;
  }
  return (current + delta + length) % length;
}

export function clampGoToFileIndex(current: number, length: number): number {
  if (length <= 0) {
    return 0;
  }
  if (current < 0) {
    return 0;
  }
  if (current >= length) {
    return length - 1;
  }
  return current;
}

function uniqueSafePaths(paths: readonly string[]): string[] {
  const seen = new Set<string>();
  const unique: string[] = [];
  for (const raw of paths) {
    const path = safeWorkspaceRelPath(raw);
    if (path === "" || seen.has(path)) {
      continue;
    }
    seen.add(path);
    unique.push(path);
  }
  return unique;
}

function filePathMatchScore(path: string, needle: string): number | null {
  const lower = path.toLowerCase();
  const basename = basenameOf(lower);
  if (basename === needle) {
    return 0;
  }
  if (basename.startsWith(needle)) {
    return 1;
  }
  if (basename.includes(needle)) {
    return 2;
  }
  if (lower.startsWith(needle)) {
    return 3;
  }
  if (lower.includes(needle)) {
    return 4;
  }
  if (hasSubsequence(basename, needle)) {
    return 5;
  }
  if (hasSubsequence(lower, needle)) {
    return 6;
  }
  return null;
}

function compareScoredPaths(
  left: { path: string; score: number },
  right: { path: string; score: number },
): number {
  if (left.score !== right.score) {
    return left.score - right.score;
  }
  const leftName = basenameOf(left.path);
  const rightName = basenameOf(right.path);
  if (leftName.length !== rightName.length) {
    return leftName.length - rightName.length;
  }
  if (left.path.length !== right.path.length) {
    return left.path.length - right.path.length;
  }
  return left.path.localeCompare(right.path, undefined, { sensitivity: "base" });
}

function basenameOf(path: string): string {
  const slash = path.lastIndexOf("/");
  return slash < 0 ? path : path.slice(slash + 1);
}

function hasSubsequence(haystack: string, needle: string): boolean {
  let from = 0;
  for (const char of needle) {
    const at = haystack.indexOf(char, from);
    if (at < 0) {
      return false;
    }
    from = at + 1;
  }
  return true;
}
