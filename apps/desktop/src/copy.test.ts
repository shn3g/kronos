// SPDX-License-Identifier: AGPL-3.0-or-later

import { readdirSync, readFileSync } from "node:fs";
import { dirname, join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// Not `new URL(".", import.meta.url)`: Vite rewrites that pattern into an http asset URL.
const ROOT = dirname(fileURLToPath(import.meta.url));
const EM_DASH = "\u2014";
const JARGON = [
  "OpenAI-compatible",
  "orchestrator",
  "billed",
  "cost ceiling",
  "risk ceiling",
  "attempt budget",
  "manifest",
  "candidates",
  "sparse",
  "graph retrieval",
  "Import pack",
];

// String literals and JSX text are the only places copy can live; identifiers
// such as an `orchestrator` object key are not user-facing and are ignored.
const VISIBLE_TEXT = /(["'`])(?:(?!\1).)*\1|>[^<{]+</g;

function isCopySource(name: string): boolean {
  return /\.(tsx|ts|css)$/.test(name) && !/\.test\.(tsx|ts)$/.test(name);
}

function walk(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) walk(path, out);
    else if (isCopySource(entry.name)) out.push(path);
  }
  return out;
}

function offendersIn(file: string): string[] {
  const label = `src/${relative(ROOT, file).split(sep).join("/")}`;
  const text = readFileSync(file, "utf8");
  const found: string[] = [];
  if (text.includes(EM_DASH)) found.push(`${label}: em dash`);
  if (file.endsWith(".css")) return found;
  const visible = (text.match(VISIBLE_TEXT)?.join("\n") ?? "").toLowerCase();
  for (const word of JARGON) {
    if (visible.includes(word.toLowerCase())) found.push(`${label}: ${word}`);
  }
  return found;
}

describe("UI copy", () => {
  it("has no em dashes or jargon in user-facing source", () => {
    const offenders = walk(ROOT).sort().flatMap(offendersIn);
    expect(offenders).toEqual([]);
  });
});
