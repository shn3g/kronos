// SPDX-License-Identifier: AGPL-3.0-or-later

import { useEffect, useState } from "react";
import type { EngineClient } from "../../../engine/client";
import {
  createProductionGitHubClient,
  type GitHubAppRole,
  type GitHubClient,
  type GitHubConnectionStatus,
  type GitHubManifests,
} from "./client";

export type { GitHubClient } from "./client";

const productionGitHub = createProductionGitHubClient();

interface GitHubPageProps {
  engineClient: EngineClient;
  githubClient?: GitHubClient;
}

export function GitHubPage({ engineClient, githubClient }: GitHubPageProps) {
  const client = githubClient ?? productionGitHub;
  const [ready, setReady] = useState(false);
  const [status, setStatus] = useState<GitHubConnectionStatus | null>(null);
  const [manifests, setManifests] = useState<GitHubManifests | null>(null);
  const [confirmRuleset, setConfirmRuleset] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
    if (!ready) {
      return;
    }
    let cancelled = false;
    void Promise.all([client.status(), client.manifests()]).then(([nextStatus, nextManifests]) => {
      if (cancelled) {
        return;
      }
      setStatus(nextStatus);
      setManifests(nextManifests);
    });
    return () => {
      cancelled = true;
    };
  }, [client, ready]);

  if (!ready) {
    return (
      <section className="github-setup">
        <p className="page-kicker">Connections</p>
        <h1 className="page-title">Connections</h1>
        <p className="page-body">
          Connect a compatible engine to create and install GitHub Apps. Setup stays closed until
          the local engine is ready.
        </p>
      </section>
    );
  }

  async function onRegister(role: GitHubAppRole, form: HTMLFormElement) {
    setError(null);
    const data = new FormData(form);
    try {
      await client.registerApp(role, {
        appId: Number(data.get("appId") || 0),
        slug: String(data.get("slug") || ""),
        privateKey: String(data.get("privateKey") || ""),
      });
      setStatus(await client.status());
    } catch {
      setError("Could not save the GitHub App.");
    }
  }

  async function onInstall(role: GitHubAppRole, form: HTMLFormElement) {
    setError(null);
    const data = new FormData(form);
    try {
      await client.recordInstallation(role, Number(data.get("installationId") || 0));
      setStatus(await client.status());
    } catch {
      setError("Could not save the installation.");
    }
  }

  async function onVerify(role: GitHubAppRole) {
    setError(null);
    try {
      await client.verify(role);
      setStatus(await client.status());
    } catch {
      setError("Could not verify the GitHub App installation.");
    }
  }

  async function onApplyRuleset() {
    setError(null);
    try {
      await client.applyRuleset({
        owner: "acme",
        repo: "app",
        reviewerIntegrationId: 1002,
        confirm: true,
      });
    } catch {
      setError("Could not apply the ruleset.");
    }
  }

  return (
    <section className="github-setup">
      <p className="page-kicker">Connections</p>
      <h1 className="page-title">Connections</h1>
      <p className="page-body">
        Create and install two GitHub Apps. Runtime uses short-lived installation tokens. GitHub
        CLI may help during setup and is not a runtime dependency.
      </p>
      <p className="github-setup__check">
        Required reviewer check:{" "}
        <code>{manifests?.reviewerCheckName ?? "kronos-review (kronos-reviewer)"}</code>
      </p>
      <p className="github-setup__meta">
        Webhooks are off. The engine polls GitHub conditionally unless you configure ingress.
      </p>
      <AppCard
        title="Controller App"
        role="controller"
        onRegister={onRegister}
        onInstall={onInstall}
        onVerify={onVerify}
      />
      <AppCard
        title="Reviewer App"
        role="reviewer"
        onRegister={onRegister}
        onInstall={onInstall}
        onVerify={onVerify}
      />
      <form
        className="wizard"
        onSubmit={(event) => {
          event.preventDefault();
          void onApplyRuleset();
        }}
      >
        <h2 className="wizard__title">Ruleset</h2>
        <p className="wizard__copy">
          Proposed rulesets require the reviewer integration id and strict required checks. Kronos
          will not add bypass actors or drop existing checks.
        </p>
        <label className="models__confirm" htmlFor="ruleset-confirm">
          <input
            id="ruleset-confirm"
            type="checkbox"
            checked={confirmRuleset}
            onChange={(event) => {
              setConfirmRuleset(event.target.checked);
            }}
          />
          I confirm this does not weaken existing protections
        </label>
        <button type="submit" className="btn-primary" disabled={!confirmRuleset}>
          Apply ruleset
        </button>
      </form>
      {error ? <p className="wizard__error">{error}</p> : null}
      {status?.githubCliPresent ? (
        <p className="github-setup__meta">GitHub CLI is present for setup assist only.</p>
      ) : null}
    </section>
  );
}

function AppCard({
  title,
  role,
  onRegister,
  onInstall,
  onVerify,
}: {
  title: string;
  role: GitHubAppRole;
  onRegister: (role: GitHubAppRole, form: HTMLFormElement) => Promise<void>;
  onInstall: (role: GitHubAppRole, form: HTMLFormElement) => Promise<void>;
  onVerify: (role: GitHubAppRole) => Promise<void>;
}) {
  const prefix = role === "controller" ? "Controller" : "Reviewer";
  return (
    <section className="wizard">
      <h2 className="wizard__title">{title}</h2>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void onRegister(role, event.currentTarget);
        }}
      >
        <label className="wizard__label" htmlFor={`${role}-app-id`}>
          {prefix} App ID
          <input id={`${role}-app-id`} className="wizard__input" name="appId" />
        </label>
        <label className="wizard__label" htmlFor={`${role}-slug`}>
          {prefix} slug
          <input id={`${role}-slug`} className="wizard__input" name="slug" />
        </label>
        <label className="wizard__label" htmlFor={`${role}-private-key`}>
          {prefix} private key
          <textarea
            id={`${role}-private-key`}
            className="wizard__input"
            name="privateKey"
            rows={4}
          />
        </label>
        <button type="submit" className="btn-primary">
          {`Save ${role} app`}
        </button>
      </form>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void onInstall(role, event.currentTarget);
        }}
      >
        <label className="wizard__label" htmlFor={`${role}-installation-id`}>
          {prefix} installation ID
          <input id={`${role}-installation-id`} className="wizard__input" name="installationId" />
        </label>
        <button type="submit" className="btn-quiet">
          {`Save ${role} installation`}
        </button>
      </form>
      <button
        type="button"
        className="btn-quiet"
        onClick={() => {
          void onVerify(role);
        }}
      >
        {`Verify ${role}`}
      </button>
    </section>
  );
}
