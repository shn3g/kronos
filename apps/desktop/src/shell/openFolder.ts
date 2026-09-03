// SPDX-License-Identifier: AGPL-3.0-or-later

import {
  pickRepositoryFolder,
  type EnrolledRepository,
  type RepositoriesClient,
} from "../features/workspaces/client";

export interface OpenFolderResult {
  repository: EnrolledRepository;
  alreadyEnrolled: boolean;
}

export interface OpenFolderOptions {
  pickFolder?: () => Promise<string | null>;
  repositories?: EnrolledRepository[];
}

export async function openRepositoryFolder(
  client: RepositoriesClient,
  options: OpenFolderOptions = {},
): Promise<OpenFolderResult | null> {
  const pick = options.pickFolder ?? pickRepositoryFolder;
  const path = await pick();
  if (!path) {
    return null;
  }

  const listed = options.repositories ?? (await client.list());
  const existing = findRepositoryByPath(listed, path);
  if (existing) {
    return { repository: existing, alreadyEnrolled: true };
  }

  const enrolled = await client.enrol(path);
  return { repository: enrolled, alreadyEnrolled: false };
}

export function findRepositoryByPath(
  repositories: EnrolledRepository[],
  path: string,
): EnrolledRepository | null {
  const target = normalizePath(path);
  return repositories.find((item) => normalizePath(item.realpath) === target) ?? null;
}

function normalizePath(path: string): string {
  return path.replace(/\\/g, "/").replace(/\/+$/, "").toLowerCase();
}
