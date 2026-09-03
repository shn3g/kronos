// SPDX-License-Identifier: AGPL-3.0-or-later

import { useEffect, useState } from "react";
import { useEngineConnection } from "../../engine/EngineConnectionProvider";
import "./workspaces.css";
import {
  createProductionRepositoriesClient,
  pickRepositoryFolder,
  type EnrolledRepository,
  type InspectResult,
  type RepositoriesClient,
} from "./client";
import { openRepositoryFolder } from "../../shell/openFolder";

export type { RepositoriesClient } from "./client";

const productionRepos = createProductionRepositoriesClient();

interface WorkspacesPageProps {
  repositoriesClient?: RepositoriesClient;
  pickFolder?: () => Promise<string | null>;
  onFolderOpened?: (repository: EnrolledRepository) => void;
}

export function WorkspacesPage({
  repositoriesClient,
  pickFolder,
  onFolderOpened,
}: WorkspacesPageProps) {
  const { engineReady: ready } = useEngineConnection();
  const client = repositoriesClient ?? productionRepos;
  const [wizardOpen, setWizardOpen] = useState(false);
  const [folderPath, setFolderPath] = useState("");
  const [inspection, setInspection] = useState<InspectResult | null>(null);
  const [repositories, setRepositories] = useState<EnrolledRepository[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!ready) {
      return;
    }
    let cancelled = false;
    void client.list().then((items) => {
      if (!cancelled) {
        setRepositories(items);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [client, ready]);

  if (!ready) {
    return (
      <section className="workspaces">
        <p className="page-kicker">Workspaces</p>
        <h1 className="page-title">Workspaces</h1>
        <p className="page-body">Waiting for the engine.</p>
      </section>
    );
  }

  async function inspectPath(path: string) {
    setError(null);
    try {
      const result = await client.inspect(path);
      setFolderPath(path);
      setInspection(result);
    } catch (error) {
      setError(error instanceof Error ? error.message : "Could not inspect that folder.");
      setInspection(null);
    }
  }

  async function onChooseFolder() {
    const chooser = pickFolder ?? pickRepositoryFolder;
    const picked = await chooser();
    if (picked) {
      await inspectPath(picked);
    }
  }

  async function onOpenFolder() {
    setError(null);
    try {
      const result = await openRepositoryFolder(client, {
        pickFolder: pickFolder ?? pickRepositoryFolder,
        repositories,
      });
      if (!result) {
        return;
      }
      setRepositories((current) => upsertRepo(current, result.repository));
      onFolderOpened?.(result.repository);
    } catch (error) {
      setError(error instanceof Error ? error.message : "Could not open that folder.");
    }
  }

  async function onEnrol() {
    if (!folderPath) {
      return;
    }
    setError(null);
    try {
      const enrolled = await client.enrol(folderPath);
      setRepositories((current) => upsertRepo(current, enrolled));
      setWizardOpen(false);
      setInspection(null);
    } catch (error) {
      setError(error instanceof Error ? error.message : "Could not enrol that repository.");
    }
  }

  async function onPause(id: string) {
    const updated = await client.pause(id);
    setRepositories((current) => upsertRepo(current, updated));
  }

  async function onDisable(id: string) {
    const updated = await client.disable(id);
    setRepositories((current) => upsertRepo(current, updated));
  }

  async function onResume(id: string) {
    const updated = await client.resume(id);
    setRepositories((current) => upsertRepo(current, updated));
  }

  function closeWizard() {
    setWizardOpen(false);
    setInspection(null);
    setFolderPath("");
    setError(null);
  }

  return (
    <section className="workspaces">
      <p className="page-kicker">Workspaces</p>
      <h1 className="page-title">Workspaces</h1>
      <p className="page-body">Open git folders so Kronos can index them and run chat and Goals.</p>
      {repositories.length === 0 ? (
        <div className="workspaces__empty-state">
          <p className="workspaces__empty">You have not opened a folder yet.</p>
          <button type="button" className="btn-primary" onClick={() => void onOpenFolder()}>
            Open a folder
          </button>
          <button type="button" className="btn-quiet" onClick={() => setWizardOpen(true)}>
            Add workspace
          </button>
          {error ? <p className="workspaces__error">{error}</p> : null}
        </div>
      ) : (
        <>
          <div className="workspaces__toolbar">
            <button type="button" className="btn-primary" onClick={() => void onOpenFolder()}>
              Open a folder
            </button>
            <button type="button" className="btn-quiet" onClick={() => setWizardOpen(true)}>
              Add workspace
            </button>
          </div>
          {error ? <p className="workspaces__error">{error}</p> : null}
        </>
      )}
      {repositories.length === 0 ? null : (
        <ul className="workspace-list">
          {repositories.map((repo) => (
            <li key={repo.id} className="workspace-card">
              <div>
                <p className="workspace-card__name">{repo.displayName}</p>
                <p className="workspace-card__meta">{repo.realpath}</p>
                <p className="workspace-card__status">{repo.status}</p>
              </div>
              <div className="workspace-card__actions">
                {repo.status !== "active" ? (
                  <button type="button" className="btn-quiet" onClick={() => void onResume(repo.id)}>
                    Resume
                  </button>
                ) : null}
                <button type="button" className="btn-quiet" onClick={() => void onPause(repo.id)}>
                  Pause
                </button>
                <button type="button" className="btn-quiet" onClick={() => void onDisable(repo.id)}>
                  Disable
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {wizardOpen ? (
        <div className="wizard">
          <h2 className="wizard__title">Add workspace</h2>
          <p className="wizard__copy">
            Choose a git folder. Kronos indexes it for chat and Goals. Policy files are preview-only
            until you commit them yourself.
          </p>
          <label className="wizard__label" htmlFor="repo-folder">
            Repository folder
          </label>
          <div className="wizard__row">
            <input
              id="repo-folder"
              className="wizard__input"
              value={folderPath}
              onChange={(event) => {
                setFolderPath(event.target.value);
                setInspection(null);
              }}
            />
            <button type="button" className="btn-quiet" onClick={() => void onChooseFolder()}>
              Choose folder
            </button>
          </div>
          {folderPath && !inspection ? (
            <button type="button" className="btn-quiet" onClick={() => void inspectPath(folderPath)}>
              Preview
            </button>
          ) : null}
          {inspection ? (
            <div className="wizard__preview">
              <p className="wizard__preview-label">Preview only. Files are not written.</p>
              {inspection.preview.map((file) => (
                <article key={file.path} className="preview-file">
                  <h3 className="preview-file__path">{file.path}</h3>
                  <pre className="preview-file__diff">{file.unifiedDiff || file.content}</pre>
                </article>
              ))}
              <button type="button" className="btn-primary" onClick={() => void onEnrol()}>
                Enrol
              </button>
            </div>
          ) : null}
          {error ? <p className="wizard__error">{error}</p> : null}
          <button type="button" className="btn-quiet" onClick={closeWizard}>
            Cancel
          </button>
        </div>
      ) : null}
    </section>
  );
}

function upsertRepo(
  current: EnrolledRepository[],
  next: EnrolledRepository,
): EnrolledRepository[] {
  const without = current.filter((item) => item.id !== next.id);
  return [...without, next];
}
