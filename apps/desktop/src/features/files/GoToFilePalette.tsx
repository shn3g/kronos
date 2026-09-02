// SPDX-License-Identifier: AGPL-3.0-or-later

import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { RepositoriesClient } from "../workspaces/client";
import {
  clampGoToFileIndex,
  nextGoToFileIndex,
  rankWorkspaceFilePaths,
} from "./goToFile";

interface GoToFilePaletteProps {
  open: boolean;
  repositoryId: string | null;
  repositoriesClient: RepositoriesClient;
  onClose: () => void;
  onOpenWorkspace: () => void;
  onSelect: (path: string) => void;
}

export function GoToFilePalette({
  open,
  repositoryId,
  repositoriesClient,
  onClose,
  onOpenWorkspace,
  onSelect,
}: GoToFilePaletteProps) {
  const labelId = useId();
  const listId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [paths, setPaths] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [highlight, setHighlight] = useState(0);
  const results = useMemo(() => rankWorkspaceFilePaths(paths, query), [paths, query]);
  const active = clampGoToFileIndex(highlight, results.length);

  useEffect(() => {
    if (!open) {
      return;
    }
    setQuery("");
    setHighlight(0);
    setPaths([]);
    setError(null);
    inputRef.current?.focus();
  }, [open]);

  useEffect(() => {
    if (!open || !repositoryId) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    void repositoriesClient.listWorkspaceFiles(repositoryId).then(
      (files) => {
        if (cancelled) {
          return;
        }
        setPaths(files.map((item) => item.path));
        setLoading(false);
      },
      () => {
        if (cancelled) {
          return;
        }
        setPaths([]);
        setLoading(false);
        setError("Could not load the file list. Check that the engine is running, then try again.");
      },
    );
    return () => {
      cancelled = true;
    };
  }, [open, repositoryId, repositoriesClient]);

  useEffect(() => {
    setHighlight(0);
  }, [query, paths]);

  useEffect(() => {
    if (!open) {
      return;
    }
    function onKey(event: KeyboardEvent): void {
      if (event.key !== "Escape") {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      onClose();
    }
    window.addEventListener("keydown", onKey, true);
    return () => {
      window.removeEventListener("keydown", onKey, true);
    };
  }, [open, onClose]);

  if (!open) {
    return null;
  }

  function choose(path: string): void {
    if (path === "") {
      return;
    }
    onSelect(path);
    onClose();
  }

  function onOpenFolder(): void {
    onOpenWorkspace();
    onClose();
  }

  const hasRepo = repositoryId !== null;
  const status = paletteStatus({
    hasRepo,
    loading,
    error,
    pathCount: paths.length,
    resultCount: results.length,
  });

  return (
    <div className="go-to-file">
      <button type="button" className="go-to-file__dismiss" aria-label="Close" onClick={onClose} />
      <div className="go-to-file__panel" role="dialog" aria-modal="true" aria-labelledby={labelId}>
        {hasRepo ? (
          <form
            className="go-to-file__form"
            onSubmit={(event) => {
              event.preventDefault();
              const path = results[active];
              if (path !== undefined) {
                choose(path);
              }
            }}
          >
            <label className="go-to-file__label" htmlFor="go-to-file-input" id={labelId}>
              Go to file
              <input
                ref={inputRef}
                id="go-to-file-input"
                type="search"
                role="combobox"
                autoComplete="off"
                spellCheck={false}
                value={query}
                aria-autocomplete="list"
                aria-expanded={results.length > 0}
                aria-controls={listId}
                aria-activedescendant={
                  results.length > 0 ? `go-to-file-option-${active}` : undefined
                }
                onChange={(event) => {
                  setQuery(event.target.value);
                }}
                onKeyDown={(event) => {
                  if (event.key === "ArrowDown") {
                    event.preventDefault();
                    setHighlight((current) => nextGoToFileIndex(current, 1, results.length));
                    return;
                  }
                  if (event.key === "ArrowUp") {
                    event.preventDefault();
                    setHighlight((current) => nextGoToFileIndex(current, -1, results.length));
                  }
                }}
              />
            </label>
          </form>
        ) : (
          <h2 className="go-to-file__title" id={labelId}>
            Go to file
          </h2>
        )}
        {status ? (
          <p className={error ? "wizard__error" : "go-to-file__status"} role={error ? "alert" : "status"}>
            {status}
          </p>
        ) : null}
        {!hasRepo ? (
          <button type="button" className="btn-quiet" onClick={onOpenFolder}>
            Open folder
          </button>
        ) : null}
        {results.length > 0 ? (
          <ul className="go-to-file__list" id={listId} role="listbox" aria-label="Workspace files">
            {results.map((path, index) => (
              <li key={path} role="presentation">
                <button
                  type="button"
                  id={`go-to-file-option-${index}`}
                  className="go-to-file__item"
                  role="option"
                  aria-selected={index === active}
                  title={path}
                  onMouseDown={(event) => {
                    event.preventDefault();
                    choose(path);
                  }}
                >
                  {path}
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </div>
  );
}

function paletteStatus(input: {
  hasRepo: boolean;
  loading: boolean;
  error: string | null;
  pathCount: number;
  resultCount: number;
}): string | null {
  if (!input.hasRepo) {
    return "Open a git folder from Workspaces to jump to a file.";
  }
  if (input.error) {
    return input.error;
  }
  if (input.loading) {
    return "Loading files.";
  }
  if (input.pathCount === 0) {
    return "This workspace has no files Kronos can list yet.";
  }
  if (input.resultCount === 0) {
    return "No matching files.";
  }
  return null;
}
