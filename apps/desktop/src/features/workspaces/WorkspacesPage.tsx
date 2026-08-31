// SPDX-License-Identifier: AGPL-3.0-or-later

import { useEffect, useState } from "react";
import type { EngineClient } from "../../engine/client";
import {
  createProductionRepositoriesClient,
  type EnrolledRepository,
  type InspectResult,
  type RepositoriesClient,
} from "./client";

export type { RepositoriesClient } from "./client";

const productionRepos = createProductionRepositoriesClient();

interface WorkspacesPageProps {
  engineClient: EngineClient;
  repositoriesClient?: RepositoriesClient;
  pickFolder?: () => Promise<string | null>;
}

export function WorkspacesPage({
  engineClient,
  repositoriesClient,
  pickFolder,
}: WorkspacesPageProps) {
  const client = repositoriesClient ?? productionRepos;
  const [ready, setReady] = useState(false);
  const [repositories, setRepositories] = useState<EnrolledRepository[]>([]);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [folderPath, setFolderPath] = useState("");
  const [inspection, setInspection] = useState<InspectResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void engineClient.getState().then((state) => {
      if (!cancelled) {
        setReady(state.status === "ready");
      }
    });
    return () => {
      cancelled = true;
    };
  }, [engineClient]);

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
        <p className="page-body">
          Connect a compatible engine to enrol repositories. Enrolment stays closed until the
          local engine is ready.
        </p>
      </section>
    );
  }

  async function inspectPath(path: string) {
    setError(null);
    try {
      const result = await client.inspect(path);
      setFolderPath(path);
      setInspection(result);
    } catch {
      setError("Could not inspect that folder.");
      setInspection(null);
    }
  }

  async function onChooseFolder() {
    if (!pickFolder) {
      return;
    }
    const picked = await pickFolder();
    if (picked) {
      await inspectPath(picked);
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
    } catch {
      setError("Could not enrol that repository.");
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

  return (
    <section className="workspaces">
      <p className="page-kicker">Workspaces</p>
      <h1 className="page-title">Workspaces</h1>
      <p className="page-body">
        Enrolled repositories stay isolated. Indexes, worktrees, and engine state live outside git.
      </p>
      <div className="workspaces__toolbar">
        <button type="button" className="btn-primary" onClick={() => setWizardOpen(true)}>
          Enable Kronos
        </button>
      </div>
      {repositories.length === 0 ? (
        <p className="workspaces__empty">No repositories enrolled yet.</p>
      ) : (
        <ul className="workspace-list">
          {repositories.map((repo) => (
            <li key={repo.id} className="workspace-card">
              <div>
                <p className="workspace-card__name">{repo.displayName}</p>
                <p className="workspace-card__meta">{repo.realpath}</p>
                <p className="workspace-card__status">{repo.status}</p>
              </div>
              <div className="workspace-card__actions">
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
          <h2 className="wizard__title">Enable Kronos</h2>
          <p className="wizard__copy">
            Choose a git folder. Kronos proposes reviewable files and does not commit or push.
          </p>
          <label className="wizard__label" htmlFor="repo-folder">
            Repository folder
          </label>
          <div className="wizard__row">
            <input
              id="repo-folder"
              className="wizard__input"
              value={folderPath}
              onChange={(event) => setFolderPath(event.target.value)}
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
