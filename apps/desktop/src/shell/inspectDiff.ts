// SPDX-License-Identifier: AGPL-3.0-or-later

export const MAX_DIFF_LINES = 500;

export type DiffLineKind = "add" | "del" | "hunk" | "meta" | "ctx";

export interface DiffLine {
  kind: DiffLineKind;
  text: string;
}

export function diffLinesFromPatch(patch: string): DiffLine[] {
  if (patch.trim() === "") {
    return [];
  }
  const raw = patch.split("\n");
  const last = raw.length - 1;
  const lines = raw[last] === "" ? raw.slice(0, last) : raw;
  const classified = lines.slice(0, MAX_DIFF_LINES).map(classifyDiffLine);
  if (lines.length <= MAX_DIFF_LINES) {
    return classified;
  }
  return [...classified, { kind: "meta", text: "Diff truncated." }];
}

function classifyDiffLine(line: string): DiffLine {
  if (
    line.startsWith("diff ") ||
    line.startsWith("index ") ||
    line.startsWith("\\") ||
    line.startsWith("--- ") ||
    line === "---" ||
    line.startsWith("+++ ") ||
    line === "+++"
  ) {
    return { kind: "meta", text: line };
  }
  if (line.startsWith("@@")) {
    return { kind: "hunk", text: line };
  }
  if (line.startsWith("+")) {
    return { kind: "add", text: line };
  }
  if (line.startsWith("-")) {
    return { kind: "del", text: line };
  }
  return { kind: "ctx", text: line };
}

export function diffLineSpokenLabel(line: DiffLine): string {
  if (line.kind === "add") {
    return `Added. ${line.text.slice(1)}`;
  }
  if (line.kind === "del") {
    return `Removed. ${line.text.slice(1)}`;
  }
  if (line.kind === "hunk") {
    return `Hunk. ${line.text}`;
  }
  return line.text;
}
