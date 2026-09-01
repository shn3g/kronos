// SPDX-License-Identifier: AGPL-3.0-or-later

import { useEffect, useState } from "react";
import type { EngineClient } from "../../../engine/client";
import {
  createProductionGitHubClient,
  type GitHubAppRole,
  type GitHubAppStatus,
  type GitHubClient,
  type GitHubConnectionStatus,
  type GitHubManifests,
  type RepositorySafety,
  type RulesetProposalView,
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
  const [proposal, setProposal] = useState<RulesetProposalView | null>(null);
  const [safety, setSafety] = useState<RepositorySafety | null>(null);
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

  useEffect(() => {
    if (!ready || !status?.enrolled || status.reviewer.appId == null) {
      return;
    }
    const enrolled = status.enrolled;
    const reviewerId = status.reviewer.appId;
    let cancelled = false;
    void client
      .proposeRuleset({
        owner: enrolled.owner,
        repo: enrolled.repo,
        reviewerIntegrationId: reviewerId,
        integrationBranch: enrolled.integrationBranch,
      })
      .then((nextProposal) => {
        if (!cancelled) {
          setProposal(nextProposal);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError("Could not propose a ruleset for the enrolled origin.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [client, ready, status]);

  useEffect(() => {
    if (!ready) {
      return;
    }
    const repositoryId = status?.enrolled?.repositoryId;
    if (!repositoryId) {
      setSafety({
        ok: false,
        checks: [
          { id: "ruleset_strict", ok: false, detail: "no enrolled GitHub origin" },
          { id: "kronos_pr_workflow", ok: false, detail: "no enrolled GitHub origin" },
          { id: "codeowners", ok: false, detail: "no enrolled GitHub origin" },
          { id: "reviewer_app", ok: false, detail: "no enrolled GitHub origin" },
        ],
      });
      return;
    }
    let cancelled = false;
    void client.safety(repositoryId).then(
      (nextSafety) => {
        if (!cancelled) {
          setSafety(nextSafety);
        }
      },
      () => {
        if (!cancelled) {
          setSafety({
            ok: false,
            checks: [
              { id: "ruleset_strict", ok: false, detail: "safety could not be loaded" },
              { id: "kronos_pr_workflow", ok: false, detail: "safety could not be loaded" },
              { id: "codeowners", ok: false, detail: "safety could not be loaded" },
              { id: "reviewer_app", ok: false, detail: "safety could not be loaded" },
            ],
          });
        }
      },
    );
    return () => {
      cancelled = true;
    };
  }, [client, ready, status]);

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

  async function onConvert(role: GitHubAppRole, form: HTMLFormElement) {
    setError(null);
    const data = new FormData(form);
    try {
      await client.convertManifest(role, String(data.get("code") || ""));
      setStatus(await client.status());
    } catch {
      setError("Could not convert the GitHub App manifest.");
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
    if (!status?.enrolled || status.reviewer.appId == null) {
      setError("Enrol a GitHub origin and convert the reviewer App first.");
      return;
    }
    try {
      await client.applyRuleset({
        owner: status.enrolled.owner,
        repo: status.enrolled.repo,
        reviewerIntegrationId: status.reviewer.appId,
        integrationBranch: status.enrolled.integrationBranch,
        confirm: confirmRuleset,
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
        appStatus={status?.controller}
        manifest={manifests?.controller}
        onConvert={onConvert}
        onInstall={onInstall}
        onVerify={onVerify}
      />
      <AppCard
        title="Reviewer App"
        role="reviewer"
        appStatus={status?.reviewer}
        manifest={manifests?.reviewer}
        onConvert={onConvert}
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
        {status?.enrolled ? (
          <p className="github-setup__meta">
            Enrolled origin: {status.enrolled.owner}/{status.enrolled.repo}
          </p>
        ) : (
          <p className="github-setup__meta">Enrol a GitHub repository before applying a ruleset.</p>
        )}
        {proposal ? (
          <>
            <p className="github-setup__meta">Strict: {proposal.strict ? "yes" : "no"}</p>
            <ul className="github-setup__checks">
              {proposal.requiredChecks.map((check) => (
                <li key={check.context}>
                  {check.context}
                  {check.integrationId != null ? ` (${check.integrationId})` : ""}
                </li>
              ))}
            </ul>
          </>
        ) : null}
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
        <button
          type="submit"
          className="btn-primary"
          disabled={!confirmRuleset || !status?.enrolled || status.reviewer.appId == null}
        >
          Apply ruleset
        </button>
      </form>
      <section className="wizard">
        <h2 className="wizard__title">Repository safety</h2>
        <p className="wizard__copy">
          Kronos will not elevate to draft PRs or merge until every check below passes.
        </p>
        <ul className="github-setup__checks">
          {(safety?.checks ?? []).map((check) => (
            <li key={check.id}>
              {check.id}: {check.ok ? "ok" : "fail"} — {check.detail}
            </li>
          ))}
        </ul>
        <p className="github-setup__meta">
          {safety?.ok
            ? "PR write modes are allowed."
            : "Mode elevation is blocked until these checks pass."}
        </p>
      </section>
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
  appStatus,
  manifest,
  onConvert,
  onInstall,
  onVerify,
}: {
  title: string;
  role: GitHubAppRole;
  appStatus: GitHubAppStatus | undefined;
  manifest: Record<string, unknown> | undefined;
  onConvert: (role: GitHubAppRole, form: HTMLFormElement) => Promise<void>;
  onInstall: (role: GitHubAppRole, form: HTMLFormElement) => Promise<void>;
  onVerify: (role: GitHubAppRole) => Promise<void>;
}) {
  const prefix = role === "controller" ? "Controller" : "Reviewer";
  const createUrl = appStatus?.createUrl || "https://github.com/settings/apps/new";
  return (
    <section className="wizard">
      <h2 className="wizard__title">{title}</h2>
      <p className="github-setup__meta">App id: {appStatus?.appId ?? "not registered"}</p>
      <p className="github-setup__meta">Slug: {appStatus?.slug ?? "not registered"}</p>
      <p className="github-setup__meta">Registered: {appStatus?.registered ? "yes" : "no"}</p>
      <p className="github-setup__meta">Installed: {appStatus?.installed ? "yes" : "no"}</p>
      <p className="github-setup__meta">Verified: {appStatus?.verified ? "yes" : "no"}</p>
      <p className="github-setup__links">
        <a href={createUrl} target="_blank" rel="noreferrer">
          {`Create ${role} App on GitHub`}
        </a>
        {appStatus?.installUrl ? (
          <a href={appStatus.installUrl} target="_blank" rel="noreferrer">
            {`Install ${role} App on GitHub`}
          </a>
        ) : null}
      </p>
      <form action={createUrl} method="post" target="_blank">
        <input type="hidden" name="manifest" value={JSON.stringify(manifest ?? {})} />
        <button type="submit" className="btn-quiet">
          {`Create ${role} App with manifest`}
        </button>
      </form>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void onConvert(role, event.currentTarget);
        }}
      >
        <label className="wizard__label" htmlFor={`${role}-manifest-code`}>
          {prefix} manifest code
          <input id={`${role}-manifest-code`} className="wizard__input" name="code" />
        </label>
        <button type="submit" className="btn-primary">
          {`Convert ${role}`}
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
