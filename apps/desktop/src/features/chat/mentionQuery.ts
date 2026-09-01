// SPDX-License-Identifier: AGPL-3.0-or-later

export interface MentionQuery {
  start: number;
  query: string;
}

export function mentionQueryAtCursor(text: string, cursor: number): MentionQuery | null {
  if (cursor < 1 || cursor > text.length) {
    return null;
  }
  const before = text.slice(0, cursor);
  const at = before.lastIndexOf("@");
  if (at < 0) {
    return null;
  }
  const previous = at === 0 ? "" : before.slice(at - 1, at);
  if (previous !== "" && /[\w.]/.test(previous)) {
    return null;
  }
  const query = before.slice(at + 1);
  if (query.includes(" ") || query.includes("\n")) {
    return null;
  }
  return { start: at, query };
}

export function insertMention(text: string, start: number, query: string, path: string): string {
  return `${text.slice(0, start)}@${path} ${text.slice(start + 1 + query.length)}`;
}

export function uniqueMentionPaths(hits: { path: string }[]): string[] {
  const seen = new Set<string>();
  const paths: string[] = [];
  for (const hit of hits) {
    if (hit.path === "" || seen.has(hit.path)) {
      continue;
    }
    seen.add(hit.path);
    paths.push(hit.path);
  }
  return paths;
}
