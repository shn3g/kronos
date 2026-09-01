// SPDX-License-Identifier: AGPL-3.0-or-later

import { useEffect, useMemo, useState, type CSSProperties } from "react";
import type { EngineClient } from "../../engine/client";
import {
  createProductionRepositoriesClient,
  type RepositoriesClient,
  type WorkspaceFileContents,
} from "../workspaces/client";
import {
  fileTreeFromPaths,
  filterFileTree,
  flattenFileTree,
  folderPathsInTree,
} from "./fileTree";

const productionRepos = createProductionRepositoriesClient();

interface FilesPageProps {
  engineClient: EngineClient;
  repositoryId: string | null;
  repositoriesClient?: RepositoriesClient;
  onOpenWorkspace: () => void;
}

export function FilesPage({
  engineClient,
  repositoryId,
  repositoriesClient,
  onOpenWorkspace,
}: FilesPageProps) {
  const client = repositoriesClient ?? productionRepos;
  const [ready, setReady] = useState(false);
  const [filter, setFilter] = useState("");
  const [paths, setPaths] = useState<string[]>([]);
  const [listError, setListError] = useState<string | null>(null);
  const [loadingList, setLoadingList] = useState(false);
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [preview, setPreview] = useState<WorkspaceFileContents | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [loadingPreview, setLoadingPreview] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const apply = () => {
      void engineClient.getState().then((state) => {
        if (!cancelled) {
          setReady(state.status === "ready");
        }
      });
    };
    apply();
    const interval = window.setInterval(apply, 1500);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [engineClient]);

  useEffect(() => {
    setFilter("");
    setSelectedPath(null);
    setPreview(null);
    setPreviewError(null);
    setExpanded(new Set());
    setPaths([]);
    setListError(null);
  }, [repositoryId]);

  useEffect(() => {
    if (!ready || !repositoryId) {
      return;
    }
    let cancelled = false;
    setLoadingList(true);
    setListError(null);
    void client.listWorkspaceFiles(repositoryId).then(
      (files) => {
        if (cancelled) {
          return;
        }
        setPaths(files.map((item) => item.path).filter((path) => path !== ""));
        setLoadingList(false);
      },
      () => {
        if (cancelled) {
          return;
        }
        setPaths([]);
        setLoadingList(false);
        setListError("Could not load the file list. Check that the engine is running, then try again.");
      },
    );
    return () => {
      cancelled = true;
    };
  }, [client, ready, repositoryId]);

  useEffect(() => {
    if (!ready || !repositoryId || !selectedPath) {
      return;
    }
    let cancelled = false;
    setLoadingPreview(true);
    setPreviewError(null);
    void client.readWorkspaceFile(repositoryId, selectedPath).then(
      (payload) => {
        if (cancelled) {
          return;
        }
        setPreview(payload);
        setLoadingPreview(false);
      },
      () => {
        if (cancelled) {
          return;
        }
        setPreview(null);
        setLoadingPreview(false);
        setPreviewError("Could not open that file. It may be outside the workspace or missing.");
      },
    );
    return () => {
      cancelled = true;
    };
  }, [client, ready, repositoryId, selectedPath]);

  const tree = useMemo(() => fileTreeFromPaths(paths), [paths]);
  const visible = useMemo(() => filterFileTree(tree, filter), [filter, tree]);
  const expandedPaths = useMemo(() => {
    if (filter.trim() !== "") {
      return new Set(folderPathsInTree(visible));
    }
    return expanded;
  }, [expanded, filter, visible]);
  const rows = useMemo(() => flattenFileTree(visible, expandedPaths), [expandedPaths, visible]);

  if (!ready) {
    return (
      <section className="files-page">
        <h1 className="page-title">Files</h1>
        <p className="page-body">Connect a compatible engine to browse workspace files.</p>
      </section>
    );
  }

  if (!repositoryId) {
    return (
      <section className="files-page">
        <h1 className="page-title">Files</h1>
        <p className="page-body">Open a git folder from Workspaces to browse files here.</p>
        <button type="button" className="btn-quiet" onClick={onOpenWorkspace}>
          Open folder
        </button>
      </section>
    );
  }

  return (
    <section className="files-page">
      <header className="files-page__header">
        <h1 className="page-title">Files</h1>
        <label className="files-page__filter" htmlFor="files-filter">
          Filter files
          <input
            id="files-filter"
            type="search"
            role="searchbox"
            value={filter}
            onChange={(event) => {
              setFilter(event.target.value);
            }}
          />
        </label>
      </header>
      {listError ? <p className="wizard__error">{listError}</p> : null}
      <div className="files-page__split">
        <div className="files-page__pane">
          {loadingList ? (
            <p className="files-page__status" aria-live="polite">
              Loading files.
            </p>
          ) : null}
          {!loadingList && paths.length === 0 && !listError ? (
            <p className="files-page__status">This workspace has no files Kronos can list yet.</p>
          ) : null}
          <div role="tree" aria-label="Workspace files" aria-busy={loadingList} className="files-page__tree">
            {rows.map((row) => (
              <button
                key={row.path}
                type="button"
                role="treeitem"
                className="files-page__item"
                style={{ ["--tree-depth"]: String(row.depth) } as CSSProperties}
                aria-expanded={row.kind === "folder" ? expandedPaths.has(row.path) : undefined}
                aria-selected={row.kind === "file" ? row.path === selectedPath : undefined}
                onClick={() => {
                  if (row.kind === "folder") {
                    setExpanded((current) => toggleExpanded(current, row.path));
                    return;
                  }
                  setSelectedPath(row.path);
                }}
              >
                {row.name}
              </button>
            ))}
          </div>
        </div>
        <div className="files-page__pane files-page__pane--preview">
          <p className="files-page__preview-kicker">Read-only preview</p>
          {previewError ? <p className="wizard__error">{previewError}</p> : null}
          {loadingPreview ? (
            <p className="files-page__status" aria-live="polite">
              Opening file.
            </p>
          ) : null}
          {!selectedPath && !loadingPreview ? (
            <p className="files-page__status">Select a file to read it.</p>
          ) : null}
          {preview && !loadingPreview ? <PreviewBody preview={preview} /> : null}
        </div>
      </div>
    </section>
  );
}

function PreviewBody({ preview }: { preview: WorkspaceFileContents }) {
  if (preview.binary) {
    return (
      <p className="files-page__status">This file is binary, so Kronos is not showing its contents.</p>
    );
  }
  return <pre className="files-page__preview-body">{preview.content}</pre>;
}

function toggleExpanded(current: ReadonlySet<string>, path: string): Set<string> {
  const next = new Set(current);
  if (next.has(path)) {
    next.delete(path);
  } else {
    next.add(path);
  }
  return next;
}
