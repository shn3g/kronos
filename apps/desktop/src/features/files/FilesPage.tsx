// SPDX-License-Identifier: AGPL-3.0-or-later

import { useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent as ReactKeyboardEvent, type RefObject } from "react";
import type { EngineClient } from "../../engine/client";
import type { IndexClient, IndexHit } from "../index/client";
import {
  createProductionRepositoriesClient,
  type RepositoriesClient,
  type WorkspaceFileContents,
} from "../workspaces/client";
import {
  editorLineLabels,
  fileDraftIsDirty,
  fileFindStatusLabel,
  FIND_IN_FILE_EVENT,
  FIND_IN_FILES_EVENT,
  findInFileText,
  GO_TO_LINE_EVENT,
  goToLineStatusLabel,
  insertEditorText,
  nextFileFindIndex,
  parseGoToLineInput,
  REPLACE_IN_FILE_EVENT,
  replaceAllInFileText,
  replaceInFileMatch,
  SAVE_FILE_EVENT,
  selectionForLineColumn,
  workspaceSearchHitLabel,
  workspaceSearchHitSnippet,
} from "./fileEditor";
import {
  fileTreeFromPaths,
  filterFileTree,
  flattenFileTree,
  folderPathsInTree,
} from "./fileTree";
import { ancestorFolderPaths, safeWorkspaceRelPath } from "./workspacePath";
import { editorLanguageFromPath, highlightEditorTokens } from "./fileHighlight";

const productionRepos = createProductionRepositoriesClient();

interface FilesPageProps {
  engineClient: EngineClient;
  repositoryId: string | null;
  repositoriesClient?: RepositoriesClient;
  indexClient?: IndexClient;
  onOpenWorkspace: () => void;
  onAskInChat?: (path: string) => void;
  onWroteFile?: () => void;
  revealRequest?: { path: string; nonce: number };
}

const EMPTY_REVEAL = { path: "", nonce: 0 };

export function FilesPage({
  engineClient,
  repositoryId,
  repositoriesClient,
  indexClient,
  onOpenWorkspace,
  onAskInChat,
  onWroteFile,
  revealRequest = EMPTY_REVEAL,
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
  const [draft, setDraft] = useState<string | null>(null);
  const [savedContent, setSavedContent] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [pendingPath, setPendingPath] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchHits, setSearchHits] = useState<IndexHit[]>([]);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [searching, setSearching] = useState(false);
  const dirty = fileDraftIsDirty(savedContent, draft);
  const dirtyRef = useRef(dirty);
  const saveRef = useRef<() => Promise<void>>(async () => undefined);
  const pageRef = useRef<HTMLElement>(null);
  const editorRef = useRef<HTMLTextAreaElement>(null);
  const findInputRef = useRef<HTMLInputElement>(null);
  const replaceInputRef = useRef<HTMLInputElement>(null);
  const goToLineInputRef = useRef<HTMLInputElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const findOpenRef = useRef(false);
  const goToLineOpenRef = useRef(false);
  const [findOpen, setFindOpen] = useState(false);
  const [replaceOpen, setReplaceOpen] = useState(false);
  const [goToLineOpen, setGoToLineOpen] = useState(false);
  const [findQuery, setFindQuery] = useState("");
  const [replaceText, setReplaceText] = useState("");
  const [matchCase, setMatchCase] = useState(false);
  const [goToLineQuery, setGoToLineQuery] = useState("");
  const [goToLineStatus, setGoToLineStatus] = useState("");
  const [findIndex, setFindIndex] = useState(0);
  const [revealTarget, setRevealTarget] = useState<{ path: string; line: number } | null>(null);
  const [searchFocusTick, setSearchFocusTick] = useState(0);
  dirtyRef.current = dirty;
  findOpenRef.current = findOpen;
  goToLineOpenRef.current = goToLineOpen;
  const findMatches = useMemo(
    () => findInFileText(draft ?? "", findQuery, { caseSensitive: matchCase }),
    [draft, findQuery, matchCase],
  );
  const activeFind =
    findMatches.length === 0 ? 0 : Math.min(findIndex, findMatches.length - 1);

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
    setDraft(null);
    setSavedContent(null);
    setSaveError(null);
    setPendingPath(null);
    setExpanded(new Set());
    setPaths([]);
    setListError(null);
    setSearchQuery("");
    setSearchHits([]);
    setSearchError(null);
    setFindOpen(false);
    setReplaceOpen(false);
    setGoToLineOpen(false);
    setFindQuery("");
    setReplaceText("");
    setMatchCase(false);
    setGoToLineQuery("");
    setGoToLineStatus("");
    setFindIndex(0);
    setRevealTarget(null);
  }, [repositoryId]);

  function openPath(path: string): void {
    const safe = safeWorkspaceRelPath(path);
    if (safe === "") {
      return;
    }
    if (safe === selectedPath) {
      setPendingPath(null);
      return;
    }
    if (dirtyRef.current) {
      setPendingPath(safe);
      return;
    }
    setPendingPath(null);
    setSelectedPath(safe);
    setPreview(null);
    setDraft(null);
    setSavedContent(null);
    setLoadingPreview(true);
    setExpanded((current) => expandAncestors(current, safe));
  }

  function openSearchHit(path: string, startLine: number): void {
    const safe = safeWorkspaceRelPath(path);
    if (safe === "") {
      return;
    }
    const line = Number.isInteger(startLine) && startLine > 0 ? startLine : 1;
    setFindOpen(false);
    setReplaceOpen(false);
    setRevealTarget({ path: safe, line });
    openPath(safe);
  }

  useEffect(() => {
    const path = safeWorkspaceRelPath(revealRequest.path);
    if (revealRequest.nonce === 0 || path === "") {
      return;
    }
    openPath(path);
  }, [revealRequest.nonce, revealRequest.path]);

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
    setDraft(null);
    setSavedContent(null);
    setSaveError(null);
    void client.readWorkspaceFile(repositoryId, selectedPath).then(
      (payload) => {
        if (cancelled) {
          return;
        }
        setPreview(payload);
        if (!payload.binary) {
          setDraft(payload.content);
          setSavedContent(payload.content);
        }
        setLoadingPreview(false);
      },
      () => {
        if (cancelled) {
          return;
        }
        setPreview(null);
        setDraft(null);
        setSavedContent(null);
        setLoadingPreview(false);
        setPreviewError("Could not open that file. It may be outside the workspace or missing.");
      },
    );
    return () => {
      cancelled = true;
    };
  }, [client, ready, repositoryId, selectedPath]);

  async function onSave(): Promise<void> {
    if (!repositoryId || !selectedPath || draft === null || preview?.binary || !dirty || saving) {
      return;
    }
    setSaving(true);
    setSaveError(null);
    try {
      await client.writeWorkspaceFile(repositoryId, selectedPath, draft);
      setSavedContent(draft);
      setPreview((current) => (current ? { ...current, content: draft } : current));
      const next = pendingPath;
      setPendingPath(null);
      onWroteFile?.();
      if (next) {
        setSelectedPath(next);
        setExpanded((current) => expandAncestors(current, next));
      }
    } catch {
      setSaveError("Could not save that file. Check that the engine is running, then try again.");
    } finally {
      setSaving(false);
    }
  }

  saveRef.current = onSave;

  useEffect(() => {
    if (!findOpen) {
      return;
    }
    if (replaceOpen) {
      replaceInputRef.current?.focus();
      replaceInputRef.current?.select();
      return;
    }
    findInputRef.current?.focus();
    findInputRef.current?.select();
  }, [findOpen, replaceOpen]);

  useEffect(() => {
    if (!goToLineOpen) {
      return;
    }
    goToLineInputRef.current?.focus();
    goToLineInputRef.current?.select();
  }, [goToLineOpen]);

  useEffect(() => {
    if (!findOpen) {
      return;
    }
    const node = editorRef.current;
    const match = findMatches[activeFind];
    if (!node || match === undefined) {
      return;
    }
    const restoreFind = document.activeElement === findInputRef.current;
    const restoreReplace = document.activeElement === replaceInputRef.current;
    node.selectionStart = match.start;
    node.selectionEnd = match.end;
    if (restoreFind) {
      findInputRef.current?.focus();
    }
    if (restoreReplace) {
      replaceInputRef.current?.focus();
    }
  }, [activeFind, findMatches, findOpen, draft]);

  useLayoutEffect(() => {
    if (
      revealTarget === null ||
      draft === null ||
      loadingPreview ||
      selectedPath !== revealTarget.path
    ) {
      return;
    }
    const node = editorRef.current;
    if (node === null) {
      return;
    }
    const next = selectionForLineColumn(draft, revealTarget.line, null);
    node.focus();
    node.selectionStart = next.start;
    node.selectionEnd = next.end;
    setRevealTarget(null);
  }, [draft, loadingPreview, revealTarget, selectedPath]);

  useEffect(() => {
    if (searchFocusTick === 0) {
      return;
    }
    searchInputRef.current?.focus();
    searchInputRef.current?.select();
  }, [searchFocusTick]);

  useEffect(() => {
    function filesHidden(): boolean {
      return pageRef.current === null || pageRef.current.closest("[hidden]") !== null;
    }
    function closeFind(): void {
      setFindOpen(false);
      setReplaceOpen(false);
      setFindQuery("");
      setReplaceText("");
      setFindIndex(0);
    }
    function closeGoToLine(): void {
      setGoToLineOpen(false);
      setGoToLineQuery("");
      setGoToLineStatus("");
    }
    function onKey(event: KeyboardEvent): void {
      const modifier = event.ctrlKey || event.metaKey;
      if (event.key.toLowerCase() === "s" && modifier && !event.altKey && !event.shiftKey) {
        event.preventDefault();
        void saveRef.current();
        return;
      }
      if (event.key.toLowerCase() === "f" && modifier && !event.altKey && !event.shiftKey) {
        if (filesHidden()) {
          return;
        }
        event.preventDefault();
        closeGoToLine();
        setFindOpen(true);
        return;
      }
      if (event.key.toLowerCase() === "h" && modifier && !event.altKey && !event.shiftKey) {
        if (filesHidden()) {
          return;
        }
        event.preventDefault();
        closeGoToLine();
        setFindOpen(true);
        setReplaceOpen(true);
        return;
      }
      if (event.key.toLowerCase() === "g" && modifier && !event.altKey && !event.shiftKey) {
        if (filesHidden()) {
          return;
        }
        event.preventDefault();
        closeFind();
        setGoToLineOpen(true);
        return;
      }
      if (
        event.key === "Escape" &&
        (findOpenRef.current || goToLineOpenRef.current) &&
        !filesHidden()
      ) {
        event.preventDefault();
        event.stopPropagation();
        closeFind();
        closeGoToLine();
      }
    }
    function onMenuSave(): void {
      void saveRef.current();
    }
    function onMenuFind(): void {
      closeGoToLine();
      setFindOpen(true);
    }
    function onMenuReplace(): void {
      closeGoToLine();
      setFindOpen(true);
      setReplaceOpen(true);
    }
    function onMenuGoToLine(): void {
      closeFind();
      setGoToLineOpen(true);
    }
    function onMenuFindInFiles(): void {
      setSearchFocusTick((current) => current + 1);
    }
    window.addEventListener("keydown", onKey, true);
    window.addEventListener(SAVE_FILE_EVENT, onMenuSave);
    window.addEventListener(FIND_IN_FILE_EVENT, onMenuFind);
    window.addEventListener(FIND_IN_FILES_EVENT, onMenuFindInFiles);
    window.addEventListener(REPLACE_IN_FILE_EVENT, onMenuReplace);
    window.addEventListener(GO_TO_LINE_EVENT, onMenuGoToLine);
    return () => {
      window.removeEventListener("keydown", onKey, true);
      window.removeEventListener(SAVE_FILE_EVENT, onMenuSave);
      window.removeEventListener(FIND_IN_FILE_EVENT, onMenuFind);
      window.removeEventListener(FIND_IN_FILES_EVENT, onMenuFindInFiles);
      window.removeEventListener(REPLACE_IN_FILE_EVENT, onMenuReplace);
      window.removeEventListener(GO_TO_LINE_EVENT, onMenuGoToLine);
    };
  }, []);

  const tree = useMemo(() => fileTreeFromPaths(paths), [paths]);
  const visible = useMemo(() => filterFileTree(tree, filter), [filter, tree]);
  const expandedPaths = useMemo(() => {
    if (filter.trim() !== "") {
      return new Set(folderPathsInTree(visible));
    }
    return expanded;
  }, [expanded, filter, visible]);
  const rows = useMemo(() => flattenFileTree(visible, expandedPaths), [expandedPaths, visible]);

  async function onSearch(): Promise<void> {
    if (!indexClient || !repositoryId) {
      return;
    }
    const query = searchQuery.trim();
    if (query === "") {
      setSearchHits([]);
      setSearchError("Type something to search this workspace.");
      return;
    }
    setSearching(true);
    setSearchError(null);
    try {
      const next = await indexClient.search(repositoryId, query);
      setSearchHits(next);
      setSearchError(next.length === 0 ? "No matching files in this workspace." : null);
    } catch {
      setSearchHits([]);
      setSearchError("Could not search this workspace. Check that the engine is running, then try again.");
    } finally {
      setSearching(false);
    }
  }

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

  const canEdit = Boolean(preview && !preview.binary && draft !== null && !loadingPreview);
  const findStatus = !canEdit
    ? "Select a file to find in it."
    : fileFindStatusLabel(findQuery, findMatches.length, activeFind);

  function stepFind(delta: number): void {
    if (findMatches.length === 0) {
      return;
    }
    setFindIndex(nextFileFindIndex(activeFind, delta, findMatches.length));
  }

  function replaceCurrentMatch(): void {
    if (draft === null || !canEdit) {
      return;
    }
    const match = findMatches[activeFind];
    if (match === undefined) {
      return;
    }
    const next = replaceInFileMatch(draft, match, replaceText);
    setDraft(next.content);
  }

  function replaceEveryMatch(): void {
    if (draft === null || !canEdit) {
      return;
    }
    const next = replaceAllInFileText(draft, findQuery, replaceText, { caseSensitive: matchCase });
    setDraft(next.content);
    setFindIndex(0);
  }

  function jumpToLine(): void {
    if (draft === null || !canEdit) {
      setGoToLineStatus("Select a file to go to a line.");
      return;
    }
    const parsed = parseGoToLineInput(goToLineQuery);
    if (parsed === null) {
      setGoToLineStatus("Enter a line number.");
      return;
    }
    const next = selectionForLineColumn(draft, parsed.line, parsed.column);
    setGoToLineStatus(goToLineStatusLabel(next.line, editorLineLabels(draft).length));
    const node = editorRef.current;
    if (node === null) {
      return;
    }
    node.focus();
    node.selectionStart = next.start;
    node.selectionEnd = next.end;
  }

  return (
    <section className="files-page" ref={pageRef}>
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
      {indexClient ? (
        <form
          className="files-page__search"
          onSubmit={(event) => {
            event.preventDefault();
            void onSearch();
          }}
        >
          <label className="files-page__filter" htmlFor="files-search">
            Search contents
            <input
              ref={searchInputRef}
              id="files-search"
              type="search"
              role="searchbox"
              value={searchQuery}
              onChange={(event) => {
                setSearchQuery(event.target.value);
              }}
            />
          </label>
          <button type="submit" className="btn-quiet" disabled={searching}>
            Search
          </button>
        </form>
      ) : null}
      {searchError ? <p className="wizard__error">{searchError}</p> : null}
      {searchHits.length > 0 ? (
        <ul className="files-page__hits">
          {searchHits.map((hit) => {
            const title = workspaceSearchHitLabel(hit.path, hit.startLine);
            const snippet = workspaceSearchHitSnippet(hit.text);
            return (
              <li key={`${hit.path}:${hit.startLine}`}>
                <button
                  type="button"
                  className="files-page__hit"
                  onClick={() => {
                    openSearchHit(hit.path, hit.startLine);
                  }}
                >
                  <span className="files-page__hit-path">{title}</span>
                  {snippet === "" ? null : <span className="files-page__hit-snip">{snippet}</span>}
                </button>
              </li>
            );
          })}
        </ul>
      ) : null}
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
                  openPath(row.path);
                }}
              >
                {row.name}
              </button>
            ))}
          </div>
        </div>
        <div className="files-page__pane files-page__pane--preview">
          <div className="files-page__preview-head">
            <p className="files-page__preview-kicker">{selectedPath ?? "File"}</p>
            <div className="files-page__preview-actions">
              {dirty ? (
                <p className="files-page__unsaved" aria-live="polite">
                  Unsaved
                </p>
              ) : null}
              {canEdit ? (
                <button
                  type="button"
                  className="btn-primary"
                  disabled={!dirty || saving}
                  onClick={() => {
                    void onSave();
                  }}
                >
                  {saving ? "Saving" : "Save"}
                </button>
              ) : null}
              {pendingPath ? (
                <button
                  type="button"
                  className="btn-quiet"
                  onClick={() => {
                    const next = pendingPath;
                    if (next === null) {
                      return;
                    }
                    setPendingPath(null);
                    setSelectedPath(next);
                    setPreview(null);
                    setDraft(null);
                    setSavedContent(null);
                    setLoadingPreview(true);
                    setExpanded((current) => expandAncestors(current, next));
                  }}
                >
                  Discard
                </button>
              ) : null}
              {selectedPath && onAskInChat ? (
                <button
                  type="button"
                  className="btn-quiet"
                  onClick={() => {
                    onAskInChat(selectedPath);
                  }}
                >
                  Ask in chat
                </button>
              ) : null}
            </div>
          </div>
          {saveError ? <p className="wizard__error">{saveError}</p> : null}
          {pendingPath ? (
            <p className="wizard__error">
              {`Save or discard changes to ${selectedPath} before opening another file.`}
            </p>
          ) : null}
          {previewError ? <p className="wizard__error">{previewError}</p> : null}
          {loadingPreview ? (
            <p className="files-page__status" aria-live="polite">
              Opening file.
            </p>
          ) : null}
          {!selectedPath && !loadingPreview ? (
            <p className="files-page__status">Select a file to open it.</p>
          ) : null}
          {findOpen ? (
            <form
              className="files-page__find"
              onSubmit={(event) => {
                event.preventDefault();
                if (document.activeElement === replaceInputRef.current) {
                  replaceCurrentMatch();
                  return;
                }
                stepFind(1);
              }}
            >
              <label className="files-page__filter" htmlFor="files-find">
                Find in file
                <input
                  ref={findInputRef}
                  id="files-find"
                  type="search"
                  role="searchbox"
                  autoComplete="off"
                  spellCheck={false}
                  value={findQuery}
                  onChange={(event) => {
                    setFindQuery(event.target.value);
                    setFindIndex(0);
                  }}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && event.shiftKey) {
                      event.preventDefault();
                      stepFind(-1);
                    }
                  }}
                />
              </label>
              <label className="files-page__check" htmlFor="files-match-case">
                <input
                  id="files-match-case"
                  type="checkbox"
                  checked={matchCase}
                  onChange={(event) => {
                    setMatchCase(event.target.checked);
                    setFindIndex(0);
                  }}
                />
                Match case
              </label>
              {replaceOpen ? (
                <label className="files-page__filter" htmlFor="files-replace">
                  Replace with
                  <input
                    ref={replaceInputRef}
                    id="files-replace"
                    type="text"
                    autoComplete="off"
                    spellCheck={false}
                    value={replaceText}
                    onChange={(event) => {
                      setReplaceText(event.target.value);
                    }}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        event.preventDefault();
                        replaceCurrentMatch();
                      }
                    }}
                  />
                </label>
              ) : null}
              {findStatus ? (
                <p className="files-page__find-status" role="status">
                  {findStatus}
                </p>
              ) : null}
              <button
                type="button"
                className="btn-quiet"
                disabled={findMatches.length === 0}
                onClick={() => {
                  stepFind(1);
                }}
              >
                Next
              </button>
              <button
                type="button"
                className="btn-quiet"
                disabled={findMatches.length === 0}
                onClick={() => {
                  stepFind(-1);
                }}
              >
                Previous
              </button>
              {replaceOpen ? (
                <>
                  <button
                    type="button"
                    className="btn-quiet"
                    disabled={findMatches.length === 0 || !canEdit}
                    onClick={() => {
                      replaceCurrentMatch();
                    }}
                  >
                    Replace
                  </button>
                  <button
                    type="button"
                    className="btn-quiet"
                    disabled={findMatches.length === 0 || !canEdit}
                    onClick={() => {
                      replaceEveryMatch();
                    }}
                  >
                    Replace all
                  </button>
                </>
              ) : null}
              <button
                type="button"
                className="btn-quiet"
                onClick={() => {
                  setFindOpen(false);
                  setReplaceOpen(false);
                  setFindQuery("");
                  setReplaceText("");
                  setFindIndex(0);
                }}
              >
                Close
              </button>
            </form>
          ) : null}
          {goToLineOpen ? (
            <form
              className="files-page__find"
              onSubmit={(event) => {
                event.preventDefault();
                jumpToLine();
              }}
            >
              <label className="files-page__filter" htmlFor="files-goto-line">
                Go to line
                <input
                  ref={goToLineInputRef}
                  id="files-goto-line"
                  type="text"
                  inputMode="numeric"
                  autoComplete="off"
                  spellCheck={false}
                  value={goToLineQuery}
                  onChange={(event) => {
                    setGoToLineQuery(event.target.value);
                  }}
                />
              </label>
              {goToLineStatus ? (
                <p className="files-page__find-status" role="status">
                  {goToLineStatus}
                </p>
              ) : null}
              <button type="submit" className="btn-quiet" disabled={!canEdit}>
                Go
              </button>
              <button
                type="button"
                className="btn-quiet"
                onClick={() => {
                  setGoToLineOpen(false);
                  setGoToLineQuery("");
                  setGoToLineStatus("");
                }}
              >
                Close
              </button>
            </form>
          ) : null}
          {preview && !loadingPreview ? (
            <EditorBody
              preview={preview}
              draft={draft}
              disabled={saving}
              editorRef={editorRef}
              onDraft={setDraft}
            />
          ) : null}
        </div>
      </div>
    </section>
  );
}

function EditorBody({
  preview,
  draft,
  disabled,
  editorRef,
  onDraft,
}: {
  preview: WorkspaceFileContents;
  draft: string | null;
  disabled: boolean;
  editorRef: RefObject<HTMLTextAreaElement | null>;
  onDraft: (value: string) => void;
}) {
  const gutterRef = useRef<HTMLOListElement>(null);
  const highlightRef = useRef<HTMLPreElement>(null);
  const language = editorLanguageFromPath(preview.path);
  const tokens = useMemo(() => {
    if (draft === null || preview.binary || language === null) {
      return null;
    }
    return highlightEditorTokens(draft, language);
  }, [draft, language, preview.binary]);
  if (preview.binary) {
    return (
      <p className="files-page__status">This file is binary, so Kronos is not showing its contents.</p>
    );
  }
  if (draft === null) {
    return null;
  }
  const labels = editorLineLabels(draft);
  return (
    <div className="files-page__editor-wrap">
      <ol className="files-page__gutter" aria-hidden="true" ref={gutterRef}>
        {labels.map((label) => (
          <li key={label}>{label}</li>
        ))}
      </ol>
      <div className="files-page__code">
        {tokens ? (
          <pre className="files-page__highlight" aria-hidden="true" ref={highlightRef}>
            {tokens.map((token, index) => (
              <span
                key={index}
                className={token.kind === "plain" ? undefined : `files-page__hl--${token.kind}`}
              >
                {token.text}
              </span>
            ))}
          </pre>
        ) : null}
        <textarea
          ref={editorRef}
          className={
            tokens
              ? "files-page__preview-body files-page__editor files-page__editor--over"
              : "files-page__preview-body files-page__editor"
          }
          aria-label={preview.path}
          spellCheck={false}
          value={draft}
          disabled={disabled}
          onChange={(event) => {
            onDraft(event.target.value);
          }}
          onScroll={(event) => {
            const top = event.currentTarget.scrollTop;
            const left = event.currentTarget.scrollLeft;
            if (gutterRef.current) {
              gutterRef.current.scrollTop = top;
            }
            if (highlightRef.current) {
              highlightRef.current.scrollTop = top;
              highlightRef.current.scrollLeft = left;
            }
          }}
          onKeyDown={(event) => {
            onEditorKeyDown(event, draft, onDraft);
          }}
        />
      </div>
    </div>
  );
}

function onEditorKeyDown(
  event: ReactKeyboardEvent<HTMLTextAreaElement>,
  draft: string,
  onDraft: (value: string) => void,
): void {
  if (event.key !== "Tab" || event.altKey || event.ctrlKey || event.metaKey) {
    return;
  }
  event.preventDefault();
  const node = event.currentTarget;
  const next = insertEditorText(draft, node.selectionStart, node.selectionEnd, "  ");
  onDraft(next.content);
  const caret = next.caret;
  window.requestAnimationFrame(() => {
    node.selectionStart = caret;
    node.selectionEnd = caret;
  });
}

function expandAncestors(current: ReadonlySet<string>, path: string): Set<string> {
  const next = new Set(current);
  for (const folder of ancestorFolderPaths(path)) {
    next.add(folder);
  }
  return next;
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
