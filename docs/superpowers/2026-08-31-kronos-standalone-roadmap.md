# Kronos Standalone Implementation Roadmap

> **License errata (2026-08-31):** Kronos is licensed under GNU AGPL v3.0. Apache-2.0 wording in this historical plan is superseded.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement each sub-plan task-by-task. This roadmap defines program order and release gates; each milestone receives its own file-level TDD plan before implementation.

**Goal:** Build Kronos as a standalone Tauri desktop application with a bundled Python background engine, first-party Telegram, multi-repository management, portable skills, local hybrid indexing, interchangeable coding executors, GitHub automation, deterministic TDD gates, isolated review, and evidence-gated learning.

**Architecture:** A Tauri desktop client and Telegram connector call one local Python control-plane API. The engine owns deterministic workflow state, per-repository indexes, model/executor routing, sandboxed work and GitHub operations; a separately credentialed reviewer independently verifies exact PR commits. Repositories contain only reviewable Kronos policy, workflow files, and optional promoted skills.

**Tech Stack:** Tauri 2, React, TypeScript, Vite, Python 3.11-3.13, FastAPI, Pydantic, SQLite WAL, httpx, tree-sitter, SQLite FTS5, pluggable local embeddings/vector storage, Telegram Bot API, GitHub Apps, PyInstaller sidecar packaging, pytest, Hypothesis, Vitest, Testing Library, Playwright, Ruff and mypy strict.

## Global Constraints

- Hermes is not installed, imported, or required.
- The signed desktop installer must include the matching Python engine; users do not install Python manually.
- Windows, macOS and Linux are first-class targets.
- Desktop, Telegram, CLI and future clients use the same authenticated local application API.
- One installation manages many repositories, with separate config, index, state, budgets, memories, worktrees and GitHub scope per repository.
- Cross-repository context and writes are disabled unless an explicit workspace group is selected.
- Mechanical policy uses deterministic code; models cannot lower risk, increase budgets, grant tools, approve themselves or change protected policy.
- Cursor is optional. The executor and model interfaces must support local/OpenAI-compatible and open-source alternatives.
- A worker never receives controller or reviewer credentials.
- Controller and reviewer use separate GitHub Apps; required checks bind to reviewer App identity and exact head SHA.
- Kronos can autonomously merge only into a configured bot integration branch in v1. Promotion to the protected default branch is human-controlled.
- Human-readable records are authoritative. Embeddings and vector indexes are rebuildable derivatives.
- Imported skills are pinned, scanned, quarantined and regression-tested; only relevant skills are loaded for a task.
- Every external write is idempotent and auditable.
- Every behavior change follows red-green-refactor and includes unhappy-path tests.
- No single “full ship” branch. Each sub-plan below produces a reviewable, independently testable vertical capability.

---

## Program structure

This product contains independent subsystems and must not be implemented from one giant prompt. Execute these sub-plans in order:

1. Repository and cross-platform shell foundation.
2. Engine state, local API and desktop-to-engine lifecycle.
3. Repository enrolment and per-repository policy.
4. Model routing, executor and sandbox contracts.
5. Local hybrid code indexing and context assembly.
6. GitHub controller App and repository automation.
7. Independent reviewer App and integration-branch merge.
8. Goal planning, deterministic workflow and TDD execution.
9. Skills, memory and evidence-gated evolution.
10. First-party Telegram.
11. Multi-repository operations, monitoring and packaging.
12. Klikday shadow migration and public release.

The first externally usable release requires sub-plans 1-10. Sub-plans may have internal alpha checkpoints, but “standalone Kronos” means the desktop, engine and Telegram are present before public release.

## Target repository layout

```text
kronos/
├── README.md
├── LICENSE
├── SECURITY.md
├── CONTRIBUTING.md
├── GOVERNANCE.md
├── pyproject.toml
├── package.json
├── pnpm-workspace.yaml
├── apps/
│   └── desktop/
│       ├── src/
│       ├── src-tauri/
│       └── tests/
├── engine/
│   ├── pyproject.toml
│   ├── src/kronos_engine/
│   │   ├── api/
│   │   ├── application/
│   │   ├── config/
│   │   ├── domain/
│   │   ├── ports/
│   │   ├── state/
│   │   ├── adapters/
│   │   ├── indexing/
│   │   ├── memory/
│   │   ├── skills/
│   │   ├── telegram/
│   │   └── observability/
│   └── tests/
├── services/
│   └── reviewer/
│       ├── pyproject.toml
│       ├── src/kronos_reviewer/
│       └── tests/
├── skills/
│   ├── core/
│   └── regression/
├── templates/
│   ├── repository/
│   └── github/
├── deploy/
│   ├── compose.yaml
│   ├── systemd/
│   ├── launchd/
│   └── windows/
├── docs/
│   ├── architecture/
│   ├── security/
│   ├── research/
│   └── superpowers/
└── .github/
    └── workflows/
```

Dependency direction:

```text
domain <- application <- ports <- adapters <- composition roots
```

- `domain` has no I/O or framework imports.
- `application` invokes typed ports.
- adapters implement one port each and do not import other adapters.
- Tauri and FastAPI are composition boundaries, not business-logic containers.
- reviewer is separately packaged and deployed.

---

## Sub-plan 0: Contain the current Klikday workflow

**Repository:** existing `klikday-dashboard`, not the new Kronos repository.

**Current files involved:**
- `scripts/agent-ops/**`
- `ops/**`
- `.github/workflows/merge-gate.yml`
- `.github/CODEOWNERS`
- `AGENTS.md`

**Deliverable:** Prevent the current embedded factory from making unsafe writes while Kronos is built.

**Work:**
- Inventory active wrappers, cron jobs, branches, worktrees, App identities, rulesets, dirty runtime files and caches.
- Keep issue invention frozen and pause every write-capable scheduled job.
- Pin or disable wrappers that currently follow a hardcoded clone/checked-out branch.
- Protect `.github/**`, `ops/**` and `scripts/agent-ops/**`.
- Require fresh-head checks and the expected reviewer App integration ID.
- Remove PAT/`GH_TOKEN` and comment/label fallbacks from independent identity.
- Add agent-ops tests to CI.
- Treat the existing Bible as historical evidence, not executable truth.

**Exit gate:** No old bot can push or merge to protected/default branches, and every remaining old write path is known and disabled or explicitly pinned.

---

## Sub-plan 1: Public repository and desktop shell

**Primary files:**
- `README.md`
- `LICENSE`
- `SECURITY.md`
- `CONTRIBUTING.md`
- `GOVERNANCE.md`
- `package.json`
- `pnpm-workspace.yaml`
- `apps/desktop/package.json`
- `apps/desktop/src/App.tsx`
- `apps/desktop/src/main.tsx`
- `apps/desktop/src-tauri/Cargo.toml`
- `apps/desktop/src-tauri/tauri.conf.json`
- `.github/workflows/ci.yml`
- `.github/workflows/security.yml`

**Deliverable:** A signed-ready Tauri shell that launches on Windows, macOS and Linux and displays engine connection state.

**Work:**
- Create empty public repository history and Apache-2.0 governance/security documents.
- Scaffold Tauri 2 + React + strict TypeScript with no product-specific code.
- Establish semantic design tokens and accessible layout primitives for Home, Workspaces, Goals, Runs, Skills, Models and Connections.
- Add frontend unit tests and one Playwright desktop smoke test.
- Add pinned cross-platform CI, dependency audit, secret scanning, SBOM and artifact build.
- Display explicit `engine unavailable`, `starting`, `ready` and `incompatible version` states.

**Exit gate:** Desktop builds and launches on all target operating systems; UI tests cover loading and failure states; no engine behavior is mocked as success.

---

## Sub-plan 2: Engine, state and lifecycle

**Primary files:**
- `engine/pyproject.toml`
- `engine/src/kronos_engine/main.py`
- `engine/src/kronos_engine/api/app.py`
- `engine/src/kronos_engine/api/models.py`
- `engine/src/kronos_engine/config/paths.py`
- `engine/src/kronos_engine/config/settings.py`
- `engine/src/kronos_engine/domain/entities.py`
- `engine/src/kronos_engine/domain/events.py`
- `engine/src/kronos_engine/domain/results.py`
- `engine/src/kronos_engine/state/database.py`
- `engine/src/kronos_engine/state/migrations.py`
- `engine/src/kronos_engine/state/event_store.py`
- `engine/src/kronos_engine/state/outbox.py`
- `engine/src/kronos_engine/state/leases.py`
- `engine/tests/unit/**`
- `engine/tests/integration/**`
- `apps/desktop/src/api/kronosClient.ts`
- `apps/desktop/src/features/engine/**`
- `apps/desktop/src-tauri/src/engine.rs`

**Deliverable:** Tauri starts and monitors a version-matched Python sidecar with a loopback-authenticated API and persistent SQLite state.

**Work:**
- Define immutable identifiers and entities for repository, goal, task, run and event.
- Resolve platform data/config/cache/log paths with no repository-relative runtime state.
- Create SQLite WAL schema, explicit migrations, event append, transactional outbox and fenced leases.
- Expose `/health`, `/version`, `/repositories`, `/goals` and `/events` through a loopback API using a per-install local token.
- Implement graceful startup/shutdown, crash recovery and incompatible-client rejection.
- Package the engine as a Tauri sidecar and capture structured logs.
- Connect desktop status and event subscription to the real engine.

**Exit gate:** Killing/restarting the engine preserves state, does not duplicate outbox actions, and the desktop recovers without user data loss.

---

## Sub-plan 3: Repository enrolment and policy

**Primary files:**
- `engine/src/kronos_engine/config/repository.py`
- `engine/src/kronos_engine/domain/policy.py`
- `engine/src/kronos_engine/application/repositories.py`
- `engine/src/kronos_engine/adapters/git/repository.py`
- `engine/src/kronos_engine/adapters/git/detection.py`
- `engine/src/kronos_engine/adapters/git/worktrees.py`
- `engine/src/kronos_engine/ports/repository.py`
- `templates/repository/config.yaml`
- `templates/github/kronos-pr.yml`
- `apps/desktop/src/features/workspaces/**`
- `engine/tests/contract/test_repository_policy.py`
- `engine/tests/integration/test_repository_enrolment.py`

**Deliverable:** The desktop **Enable Kronos** wizard registers multiple repositories, proposes reviewable repo files and keeps indexes/state outside git.

**Work:**
- Detect git root, origin, current/default branches, languages, package managers and candidate commands.
- Define a versioned strict schema for branches, commands, autonomy, paths, risk, budgets, WIP, executor profile and indexing.
- Generate `.kronos/config.yaml`, workflow and CODEOWNERS changes as a previewable diff.
- Never commit or push generated files automatically during onboarding.
- Persist global repository records with stable IDs and realpath/symlink validation.
- Add pause, disable, remove and re-enrol semantics without deleting source code.
- Keep one repository's config, state and operations inaccessible to another repository ID.

**Exit gate:** Two fixture repos can be enrolled, restarted and independently configured with no runtime files added to either working tree.

---

## Sub-plan 4: Models, executors and sandbox contracts

**Primary files:**
- `engine/src/kronos_engine/domain/models.py`
- `engine/src/kronos_engine/ports/model_provider.py`
- `engine/src/kronos_engine/ports/executor.py`
- `engine/src/kronos_engine/ports/sandbox.py`
- `engine/src/kronos_engine/application/model_profiles.py`
- `engine/src/kronos_engine/adapters/models/openai_compatible.py`
- `engine/src/kronos_engine/adapters/executors/cursor.py`
- `engine/src/kronos_engine/adapters/executors/controlled.py`
- `engine/src/kronos_engine/adapters/sandboxes/container.py`
- `engine/src/kronos_engine/adapters/sandboxes/local_unsafe.py`
- `apps/desktop/src/features/models/**`
- `engine/tests/contract/test_model_provider.py`
- `engine/tests/contract/test_executor.py`
- `engine/tests/security/test_sandbox_capabilities.py`

**Deliverable:** Users assign explicit planner, coder, reviewer and embedding profiles; Kronos can execute a bounded synthetic task through interchangeable workers.

**Work:**
- Detect Cursor CLI and local OpenAI-compatible endpoints without executing untrusted repository code.
- Persist provider configuration separately from secret values.
- Store secrets in OS credential storage and pass only scoped, short-lived values to adapters.
- Enforce approved model/fallback lists, token/attempt/time limits and cost ceilings.
- Define executor input/output including repository/task IDs, worktree, context, capabilities, artifacts, result and usage metadata.
- Implement a controlled open executor and optional Cursor adapter.
- Create a secret-free, network-off, non-root, resource-limited default sandbox.
- Mark local unsandboxed execution visibly unsafe and disable it for autonomous merges.

**Exit gate:** The same fixture contract passes with two executors; unapproved fallback, secret access, path escape and unlimited retries fail deterministically.

---

## Sub-plan 5: Hybrid repository index

**Primary files:**
- `engine/src/kronos_engine/ports/embedding.py`
- `engine/src/kronos_engine/indexing/scanner.py`
- `engine/src/kronos_engine/indexing/chunks.py`
- `engine/src/kronos_engine/indexing/languages.py`
- `engine/src/kronos_engine/indexing/sparse.py`
- `engine/src/kronos_engine/indexing/dense.py`
- `engine/src/kronos_engine/indexing/graph.py`
- `engine/src/kronos_engine/indexing/fusion.py`
- `engine/src/kronos_engine/indexing/context.py`
- `engine/src/kronos_engine/indexing/service.py`
- `engine/src/kronos_engine/adapters/embeddings/local.py`
- `engine/tests/retrieval/**`
- `apps/desktop/src/features/index/**`

**Deliverable:** Every enrolled repository has an isolated, incremental sparse+dense+graph index and measurable context retrieval.

**Work:**
- Respect gitignore, policy excludes, generated/vendor/binary limits, file-size caps and secret patterns.
- Provide generic UTF-8 chunks plus initial tree-sitter Python/JavaScript/TypeScript symbol adapters.
- Persist path, lines, symbol, kind, language, commit, hash, relationships and trust metadata.
- Implement FTS5/BM25 exact search.
- Implement a pinned local code embedding provider; use MiniLM only for English issue/document retrieval.
- Hide vector storage behind a port and preserve sparse/graph degraded operation.
- Build definition/reference/import/test graph and a token-budgeted repo map.
- Fuse ranks using RRF and expose provenance for every context item.
- Incrementally process add/change/delete/rename by commit.
- Publish golden-query Recall@k, MRR, cold/warm latency, index time and disk size on named hardware.

**Exit gate:** Hybrid search matches or beats sparse-only on the checked-in evaluation set; repositories never cross-contaminate; secrets/deleted chunks never appear.

---

## Sub-plan 6: GitHub controller

**Primary files:**
- `engine/src/kronos_engine/ports/forge.py`
- `engine/src/kronos_engine/adapters/github/auth.py`
- `engine/src/kronos_engine/adapters/github/client.py`
- `engine/src/kronos_engine/adapters/github/issues.py`
- `engine/src/kronos_engine/adapters/github/discussions.py`
- `engine/src/kronos_engine/adapters/github/branches.py`
- `engine/src/kronos_engine/adapters/github/pulls.py`
- `engine/src/kronos_engine/adapters/github/checks.py`
- `engine/src/kronos_engine/adapters/github/rulesets.py`
- `engine/src/kronos_engine/application/github_setup.py`
- `templates/github/controller-app-manifest.json`
- `templates/github/reviewer-app-manifest.json`
- `apps/desktop/src/features/connections/github/**`
- `engine/tests/contract/test_forge_adapter.py`
- `engine/tests/integration/test_github_fixture.py`

**Deliverable:** Guided GitHub App setup and idempotent issue/discussion/branch/draft-PR operations without depending on the user's `gh` login.

**Work:**
- Create controller/reviewer App manifest onboarding and installation verification.
- Mint short-lived installation tokens and never place tokens in git remotes or logs.
- Implement pagination, ETags, timeouts, 403/429/5xx backoff and typed errors.
- Add idempotency keys/provenance markers for all comments, labels, issues, discussions and PRs.
- Create feature branches from the configured integration head and draft PRs targeting only integration.
- Propose and verify rulesets; do not silently weaken existing protections.
- Poll conditionally by default; make webhook ingress optional.

**Exit gate:** Replaying every controller command against the GitHub fixture produces one logical external action and never writes to the protected default branch.

---

## Sub-plan 7: Independent reviewer and integration merge

**Primary files:**
- `services/reviewer/pyproject.toml`
- `services/reviewer/src/kronos_reviewer/main.py`
- `services/reviewer/src/kronos_reviewer/auth.py`
- `services/reviewer/src/kronos_reviewer/attestation.py`
- `services/reviewer/src/kronos_reviewer/checkout.py`
- `services/reviewer/src/kronos_reviewer/policy.py`
- `services/reviewer/src/kronos_reviewer/verification.py`
- `services/reviewer/src/kronos_reviewer/check_run.py`
- `services/reviewer/tests/**`
- `deploy/compose.yaml`
- `engine/src/kronos_engine/domain/attestations.py`
- `engine/src/kronos_engine/application/merge.py`
- `engine/tests/security/test_reviewer_identity.py`

**Deliverable:** A worker/controller cannot approve its own PR; eligible PRs auto-merge only into integration after fresh independent evidence.

**Work:**
- Define signed versioned run attestations without hidden reasoning or secrets.
- Deploy reviewer with a separate filesystem, credential and GitHub App.
- Fetch exact head/base commits independently and load trusted policy from base.
- Recalculate risk, inspect protected-path changes and rerun required commands in a fresh sandbox.
- Publish one App-bound required check using the expected integration ID.
- Reject stale/replayed attestations, wrong App identity, check-name spoofing, untrusted policy and post-review pushes.
- Merge only when all required checks are fresh, review threads resolved and autonomy policy permits.
- Generate but never auto-merge promotion PRs to the protected default branch.

**Exit gate:** Security tests demonstrate that worker, controller, stale SHA, copied comment, label and same-named foreign check cannot satisfy merge policy.

---

## Sub-plan 8: Goal engine and TDD workflow

**Primary files:**
- `engine/src/kronos_engine/domain/goals.py`
- `engine/src/kronos_engine/domain/tasks.py`
- `engine/src/kronos_engine/domain/budgets.py`
- `engine/src/kronos_engine/domain/risk.py`
- `engine/src/kronos_engine/domain/workflow.py`
- `engine/src/kronos_engine/application/goals.py`
- `engine/src/kronos_engine/application/planning.py`
- `engine/src/kronos_engine/application/dispatch.py`
- `engine/src/kronos_engine/application/verification.py`
- `engine/src/kronos_engine/application/recovery.py`
- `engine/src/kronos_engine/state/scheduler.py`
- `apps/desktop/src/features/goals/**`
- `apps/desktop/src/features/runs/**`
- `engine/tests/e2e/test_goal_to_integration_pr.py`

**Deliverable:** A bounded goal progresses through evidence-backed task planning, isolated red-green coding, CI/reviewer and eligible integration merge.

**Work:**
- Define explicit goal/task states, stop conditions and invalid-transition errors.
- Require repository, success criteria, non-goals, budget, risk ceiling and schedule/source.
- Let planners return schema-valid DAGs only; deterministic code checks cycles, evidence, scope, WIP, size, risk and budget.
- Resolve evidence against the indexed commit.
- Claim tasks transactionally with fencing leases and one writer per configured area.
- Require a failing/reproduction test artifact before accepting implementation completion, with explicit exemptions for docs/config-only tasks.
- Run configured gates and bounded repair loops.
- Pause with actionable evidence after breaker/uncertainty/attempt limits.
- Persist and stream every state transition to Desktop.
- Support goal sources: Desktop, local API/CLI, GitHub issue and deterministic schedule.

**Exit gate:** Happy, failing-test, no-test, CI-fail, model-outage, restart, conflict and budget-exhaustion scenarios all produce bounded, explainable outcomes.

---

## Sub-plan 9: Skills and evidence-gated memory

**Primary files:**
- `engine/src/kronos_engine/skills/manifest.py`
- `engine/src/kronos_engine/skills/loader.py`
- `engine/src/kronos_engine/skills/catalog.py`
- `engine/src/kronos_engine/skills/quarantine.py`
- `engine/src/kronos_engine/skills/router.py`
- `engine/src/kronos_engine/skills/evaluation.py`
- `engine/src/kronos_engine/memory/records.py`
- `engine/src/kronos_engine/memory/episodic.py`
- `engine/src/kronos_engine/memory/procedural.py`
- `engine/src/kronos_engine/memory/promotion.py`
- `skills/core/**`
- `skills/regression/**`
- `apps/desktop/src/features/skills/**`
- `apps/desktop/src/features/memory/**`
- `engine/tests/security/test_skill_quarantine.py`
- `engine/tests/integration/test_skill_promotion.py`

**Deliverable:** A curated Agent Skills-compatible library, safe imports, relevant-skill routing and auditable learning from verified outcomes.

**Work:**
- Define supported Agent Skills manifest/frontmatter and capability declarations.
- Ship 15-25 focused engineering skills with regression prompts and verification contracts.
- Fetch community skills only at immutable revisions; scan referenced files/scripts/assets and display permissions.
- Install into quarantine, run regression/security evaluation and require approval before activation.
- Load only routed skill summaries/full instructions within explicit context budgets.
- Store human-readable episodic and procedural records with source SHAs, outcomes and confidence.
- Embed records for retrieval while preserving text as source of truth.
- Promote repo-scoped skills only after configured independent helpful outcomes and zero unresolved harmful outcomes.
- Require human approval for global/core skill changes; rollback implicated skills after revert/harm.

**Exit gate:** Imported malicious skills remain quarantined, irrelevant skills do not enter context, useful skills pass regression promotion and harmful skills disable/rollback.

---

## Sub-plan 10: First-party Telegram

**Primary files:**
- `engine/src/kronos_engine/telegram/client.py`
- `engine/src/kronos_engine/telegram/auth.py`
- `engine/src/kronos_engine/telegram/commands.py`
- `engine/src/kronos_engine/telegram/formatting.py`
- `engine/src/kronos_engine/telegram/artifacts.py`
- `engine/src/kronos_engine/application/notifications.py`
- `apps/desktop/src/features/connections/telegram/**`
- `engine/tests/contract/test_telegram_commands.py`
- `engine/tests/security/test_telegram_authorization.py`

**Deliverable:** Approved Telegram users can create goals and manage/observe work through the same application services as Desktop.

**Work:**
- Guide BotFather setup and store the token in OS credential storage.
- Require explicit allowed Telegram user/chat IDs.
- Implement goal, status, pause, resume, approval and help commands.
- Require explicit repository selection or a safe configured default.
- Deduplicate Telegram updates and recover polling offsets after restart.
- Send concise state changes, PR links, failures, budget/breaker alerts and supported artifacts.
- Never place GitHub/reviewer secrets or uncontrolled log output in messages.
- Rate-limit commands and approvals.

**Exit gate:** Unauthorized users, replayed updates and ambiguous repository commands fail safely; Desktop and Telegram produce identical engine state transitions.

---

## Sub-plan 11: Operations, desktop completion and installers

**Primary files:**
- `engine/src/kronos_engine/observability/events.py`
- `engine/src/kronos_engine/observability/logging.py`
- `engine/src/kronos_engine/observability/redaction.py`
- `engine/src/kronos_engine/observability/otel.py`
- `engine/src/kronos_engine/application/doctor.py`
- `apps/desktop/src/features/home/**`
- `apps/desktop/src/features/settings/**`
- `apps/desktop/src/features/updates/**`
- `apps/desktop/src/features/notifications/**`
- `deploy/windows/**`
- `deploy/systemd/**`
- `deploy/launchd/**`
- `.github/workflows/release.yml`
- `tests/chaos/**`

**Deliverable:** Production-operable multi-repository app with health, backup, restore, updates, alerts and signed installers.

**Work:**
- Complete global dashboard, repository switcher, schedules, budgets, runs, diffs, tests and index health.
- Emit structured events/spans for policy, retrieval, model/tool calls, git, CI/review and external writes.
- Redact tokens, environment values, customer data and high-entropy secrets before persistence/export.
- Add local metrics and optional OpenTelemetry/Langfuse export.
- Implement `doctor`, backup/restore, dead-letter inspection, stuck-lease recovery and model/index degradation.
- Add chaos tests for process kill, model outage, GitHub throttling, CI timeout, disk full, corrupt cache, merge conflict and reviewer outage.
- Build signed Windows/macOS/Linux installers with checksums, SBOM and provenance.
- Test install, upgrade, incompatible-version refusal and rollback.

**Exit gate:** Operators can explain and replay every side effect without secrets; dependency failures pause safely; install/update/rollback pass on clean machines.

---

## Sub-plan 12: Klikday migration and release

**Existing Klikday inputs:**
- `ops/workflow.yaml`
- `ops/TICKET.template.md`
- `scripts/agent-ops/policy.json`
- selected useful contracts from `scripts/agent-ops/**`

**Deliverable:** Klikday runs exclusively through standalone Kronos and the public release is supported by real dogfood evidence.

**Work:**
- Translate Klikday-specific branches, commands, budgets, locked areas, risk rules and executor profile into `.kronos/config.yaml`.
- Keep `main-openclaw` as integration during cutover; do not introduce a third branch before history reconciliation.
- Import existing lessons as disabled candidates, not trusted global memory.
- Run staged modes: observe, shadow, issue/draft-PR writes, eligible integration merges, then bounded multi-task goals.
- Compare old/new decisions and outcomes for at least 50 representative tasks or 30 calendar days.
- Require zero default-branch writes, reviewer violations, duplicate external writes and secret leaks.
- Disable old wrappers/crons after two stable Kronos release cycles.
- Remove embedded generic automation from Klikday in a dedicated cleanup PR.
- Publish quickstart, architecture, threat model, model/executor profiles, GitHub Apps, Telegram, skills, retrieval metrics, operations and examples.

**Exit gate:** Kronos is the sole automation source of truth for Klikday, rollback is documented and tested, and no critical/high security findings remain.

---

## Release progression

### Internal alpha

Sub-plans 1-5:
- Desktop and engine run.
- Multiple repositories enrol.
- Model/executor profiles work.
- Local indexes are measurable.
- No autonomous GitHub writes.

### Private beta

Sub-plans 6-10:
- GitHub Apps, goals, TDD, reviewer and integration merge work.
- Skills/memory and Telegram are present.
- Klikday runs in observe/shadow mode.

### Public v1

Sub-plans 11-12:
- Signed cross-platform installers.
- Stable upgrade/rollback.
- Klikday dogfood evidence.
- Published retrieval and safety results.
- Autonomous integration-branch work, human default-branch promotion.

## Definition of done

- Kronos installs as one standalone desktop product with no Hermes dependency.
- Desktop can close while the background engine continues bounded work.
- Telegram is first-party and uses the same application services as Desktop.
- One installation manages many isolated repositories.
- Enable Kronos creates a reviewed per-repo constitution and no runtime junk.
- Cheap/local planners and replaceable coding executors are explicit and budgeted.
- Each repository has an isolated sparse+dense+graph code index.
- Skills are curated/routed; community imports are quarantined and tested.
- Workers cannot approve themselves or access controller/reviewer credentials.
- TDD, CI, exact-SHA independent review and integration-only merge are enforced in code and GitHub.
- Memories remain readable/auditable and skill evolution is evidence-gated/reversible.
- Failures are bounded, observable, recoverable and idempotent.
- Klikday no longer contains the generic factory implementation.

