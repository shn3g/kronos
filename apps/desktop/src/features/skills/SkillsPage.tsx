// SPDX-License-Identifier: AGPL-3.0-or-later

import { useEffect, useState } from "react";
import { useEngineConnection } from "../../engine/EngineConnectionProvider";
import {
  createProductionSkillsClient,
  type SkillRecord,
  type SkillsClient,
} from "./client";

export type { SkillsClient } from "./client";

interface SkillsPageProps {
  skillsClient?: SkillsClient;
}

const productionSkills = createProductionSkillsClient();

export function SkillsPage({ skillsClient }: SkillsPageProps) {
  const client = skillsClient ?? productionSkills;
  const { engineReady: ready } = useEngineConnection();
  const [skills, setSkills] = useState<SkillRecord[]>([]);
  const [locator, setLocator] = useState("");
  const [revision, setRevision] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!ready) {
      return;
    }
    let cancelled = false;
    void client.list().then((items) => {
      if (!cancelled) {
        setSkills(items);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [client, ready]);

  if (!ready) {
    return (
      <section className="skills-page">
        <p className="page-kicker">Skills</p>
        <h1 className="page-title">Skills</h1>
        <p className="page-body">Waiting for the engine.</p>
      </section>
    );
  }

  async function refresh() {
    setSkills(await client.list());
  }

  async function onImport() {
    setError(null);
    try {
      await client.importPack(locator, revision);
      setLocator("");
      setRevision("");
      await refresh();
    } catch {
      setError("Could not import the skill pack.");
    }
  }

  async function run(action: (id: string) => Promise<SkillRecord>, id: string) {
    setError(null);
    try {
      await action(id);
      await refresh();
    } catch {
      setError("The engine refused that skill action.");
    }
  }

  return (
    <section className="skills-page">
      <p className="page-kicker">Skills</p>
      <h1 className="page-title">Skills</h1>
      <p className="page-body">
        Core skills load from the curated library. Community packs stay quarantined until scan,
        regression, and approval pass. Malicious imports cannot activate.
      </p>
      <div className="skills-page__import">
        <label className="index-page__field">
          Locator
          <input
            className="wizard__input"
            value={locator}
            onChange={(event) => setLocator(event.target.value)}
          />
        </label>
        <label className="index-page__field">
          Immutable revision
          <input
            className="wizard__input"
            value={revision}
            onChange={(event) => setRevision(event.target.value)}
          />
        </label>
        <button type="button" className="btn-primary" onClick={() => void onImport()}>
          Import pack
        </button>
      </div>
      {error ? <p className="wizard__error">{error}</p> : null}
      {skills.length ? (
        <ul className="skills-page__list">
          {skills.map((skill) => (
            <li key={skill.id} className="workspace-card">
              <p className="workspace-card__name">{skill.name}</p>
              <p className="workspace-card__meta">
                {skill.status}
                {skill.scan.malicious ? " · quarantined malicious" : ""}
                {` · ${skill.scope}`}
              </p>
              <p className="workspace-card__status">{skill.description}</p>
              {skill.capabilities.length ? (
                <p className="workspace-card__meta">
                  Capabilities: {skill.capabilities.join(", ")}
                </p>
              ) : null}
              {skill.scan.files.length ? (
                <p className="workspace-card__meta">Files: {skill.scan.files.join(", ")}</p>
              ) : null}
              {skill.scan.scripts.length ? (
                <p className="workspace-card__meta">Scripts: {skill.scan.scripts.join(", ")}</p>
              ) : null}
              {skill.scan.findings.length ? (
                <p className="workspace-card__meta">
                  Findings: {skill.scan.findings.map((item) => item.code).join(", ")}
                </p>
              ) : null}
              {skill.scan.permissions.length ? (
                <p className="workspace-card__meta">
                  Permissions: {skill.scan.permissions.join(", ")}
                </p>
              ) : null}
              <div className="skills-page__actions">
                <button
                  type="button"
                  className="btn-quiet"
                  onClick={() => void run((id) => client.evaluate(id), skill.id)}
                >
                  Evaluate
                </button>
                <button
                  type="button"
                  className="btn-quiet"
                  onClick={() => void run((id) => client.approve(id, true), skill.id)}
                >
                  Approve
                </button>
                <button
                  type="button"
                  className="btn-primary"
                  disabled={skill.scan.malicious || skill.status === "quarantined"}
                  onClick={() => void run((id) => client.activate(id), skill.id)}
                >
                  Activate
                </button>
                {skill.scope === "core" || skill.scope === "global" ? (
                  <button
                    type="button"
                    className="btn-quiet"
                    onClick={() => void run((id) => client.promote(id, true), skill.id)}
                  >
                    Promote
                  </button>
                ) : null}
                <button
                  type="button"
                  className="btn-quiet"
                  onClick={() => void run((id) => client.disable(id), skill.id)}
                >
                  Disable
                </button>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="page-body">No skills are installed yet.</p>
      )}
    </section>
  );
}
