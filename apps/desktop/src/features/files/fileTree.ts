// SPDX-License-Identifier: AGPL-3.0-or-later

export type FileTreeKind = "file" | "folder";

export interface FileTreeNode {
  name: string;
  path: string;
  kind: FileTreeKind;
  children: FileTreeNode[];
}

export interface FileTreeRow {
  name: string;
  path: string;
  kind: FileTreeKind;
  depth: number;
}

export function fileTreeFromPaths(paths: readonly string[]): FileTreeNode[] {
  const root: FileTreeNode[] = [];
  for (const raw of paths) {
    const parts = posixParts(raw);
    if (parts === null) {
      continue;
    }
    insertParts(root, parts, []);
  }
  return sortTree(root);
}

export function filterFileTree(nodes: readonly FileTreeNode[], query: string): FileTreeNode[] {
  const needle = query.trim().toLowerCase();
  if (needle === "") {
    return nodes.map(cloneNode);
  }
  const kept: FileTreeNode[] = [];
  for (const node of nodes) {
    const selfMatch =
      node.name.toLowerCase().includes(needle) || node.path.toLowerCase().includes(needle);
    if (node.kind === "file") {
      if (selfMatch) {
        kept.push(cloneNode(node));
      }
      continue;
    }
    const children = filterFileTree(node.children, query);
    if (selfMatch) {
      kept.push({ ...node, children: node.children.map(cloneNode) });
      continue;
    }
    if (children.length > 0) {
      kept.push({ ...node, children });
    }
  }
  return kept;
}

export function flattenFileTree(
  nodes: readonly FileTreeNode[],
  expanded: ReadonlySet<string>,
): FileTreeRow[] {
  const rows: FileTreeRow[] = [];
  walkRows(nodes, 0, expanded, rows);
  return rows;
}

export function folderPathsInTree(nodes: readonly FileTreeNode[]): string[] {
  const paths: string[] = [];
  for (const node of nodes) {
    if (node.kind !== "folder") {
      continue;
    }
    paths.push(node.path, ...folderPathsInTree(node.children));
  }
  return paths;
}

function posixParts(raw: string): string[] | null {
  const posix = raw.replaceAll("\\", "/").replace(/^\/+/, "");
  if (posix === "") {
    return null;
  }
  const parts = posix.split("/").filter((part) => part !== "" && part !== ".");
  if (parts.length === 0 || parts.some((part) => part === "..")) {
    return null;
  }
  return parts;
}

function insertParts(nodes: FileTreeNode[], parts: readonly string[], ancestors: readonly string[]): void {
  const head = parts[0];
  if (head === undefined) {
    return;
  }
  const rest = parts.slice(1);
  const path = [...ancestors, head].join("/");
  const existing = nodes.find((item) => item.name === head);
  if (existing === undefined) {
    const created: FileTreeNode = {
      name: head,
      path,
      kind: rest.length === 0 ? "file" : "folder",
      children: [],
    };
    nodes.push(created);
    if (rest.length > 0) {
      insertParts(created.children, rest, [...ancestors, head]);
    }
    return;
  }
  if (rest.length > 0) {
    existing.kind = "folder";
    insertParts(existing.children, rest, [...ancestors, head]);
  }
}

function sortTree(nodes: FileTreeNode[]): FileTreeNode[] {
  return [...nodes]
    .sort(compareNodes)
    .map((node) => ({ ...node, children: sortTree(node.children) }));
}

function compareNodes(left: FileTreeNode, right: FileTreeNode): number {
  if (left.kind !== right.kind) {
    return left.kind === "folder" ? -1 : 1;
  }
  return left.name.localeCompare(right.name, undefined, { sensitivity: "base" });
}

function cloneNode(node: FileTreeNode): FileTreeNode {
  return { ...node, children: node.children.map(cloneNode) };
}

function walkRows(
  nodes: readonly FileTreeNode[],
  depth: number,
  expanded: ReadonlySet<string>,
  rows: FileTreeRow[],
): void {
  for (const node of nodes) {
    rows.push({ name: node.name, path: node.path, kind: node.kind, depth });
    if (node.kind === "folder" && expanded.has(node.path)) {
      walkRows(node.children, depth + 1, expanded, rows);
    }
  }
}
