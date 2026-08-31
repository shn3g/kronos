# Kronos Standalone Product Design

**Date:** 2026-08-31  
**Status:** Approved architecture, awaiting written-spec review

## Vision

Kronos is a standalone local software-engineering operating system. A user installs one desktop application, connects GitHub and Telegram, enrols one or more repositories, assigns models to engineering roles, and submits goals. Kronos then plans bounded work, retrieves repository context, delegates coding to interchangeable executors, enforces TDD and repository checks, obtains independent review, and merges eligible work into a bot-owned integration branch.

Hermes is not a dependency. Compatibility with Hermes may be offered later as an optional adapter, but Kronos owns its desktop experience, Telegram integration, scheduler, skills, memory, indexing, orchestration, GitHub integration, and enforcement.

## Product principles

1. **Simple outside, strict inside.** Installation and onboarding should feel like one application even though UI, engine, sandboxes, and reviewer are isolated internally.
2. **Models propose; code decides.** Budgets, permissions, task states, retries, required tests, and merge eligibility are deterministic.
3. **Workers are replaceable.** Cursor CLI, OpenHands, and local or hosted coding models implement the same executor contract.
4. **Tests are the primary critic.** A model reviewing another model is supplementary, not sufficient.
5. **No self-issued approval.** The coding worker and controller cannot publish the required reviewer check.
6. **Repository isolation by default.** Code, memories, budgets, indexes, and permissions do not leak between repositories.
7. **Learning remains auditable.** Human-readable records are authoritative; vectors are disposable search indexes.
8. **Autonomy is bounded.** Kronos may merge into its integration branch, while promotion into the protected default branch remains human-controlled in v1.

## What Kronos is not

- It is not a Cursor IDE clone.
- It is not a general personal assistant or Hermes clone.
- It is not a collection of markdown prompts that models may ignore.
- It does not promise that autonomous models always produce good code.
- It does not allow workers to rewrite security policy, increase their own budgets, or approve their own changes.

## User-facing product

The first usable release includes:

- A Tauri desktop application.
- A bundled Python engine running as a background user service.
- Built-in Telegram Bot API integration.
- A local authenticated API and recovery CLI.
- GitHub repository onboarding.
- A multi-repository dashboard.
- Configurable model and executor routing.
- Per-repository local code indexes.
- A curated engineering skill library.
- Goal, task, run, test, review, memory, and budget views.

The desktop application remains a client of the engine. Closing the window does not stop scheduled or active work. A future web or mobile client can use the same API without creating a second control plane.

## Internal architecture

### Desktop

The Tauri frontend provides onboarding, goals, task/run visualization, diffs, test results, skills, models, repository management, credentials status, schedules, notifications, and updates. It contains no merge policy or GitHub private keys.

### Engine

The Python engine owns:

- repository registry;
- persistent scheduler;
- goal and task state machines;
- policy, risk, effort, WIP, budget, retry, lease, and circuit-breaker decisions;
- model routing;
- repository indexing and context assembly;
- executor and sandbox dispatch;
- GitHub operations through the controller App;
- run/event history;
- memory and skill evaluation;
- Telegram commands and notifications.

### Reviewer

The reviewer runs as a separately credentialed process or container. It independently checks the exact PR head, reads trusted policy from the base branch, reruns required checks in a clean environment, verifies provenance, and publishes the required GitHub check through a reviewer App. It cannot push or merge.

### Executors

Executors receive a bounded task, worktree, context pack, capability set, limits, and required artifacts. Initial adapters are:

- a controlled OpenAI-compatible executor suitable for local endpoints;
- Cursor CLI for users who have Cursor;
- OpenHands or SWE-ReX-based execution as an open-source option.

No executor receives controller or reviewer credentials.

## Packaging

The recommended implementation is Tauri plus a bundled Python sidecar/service:

- Tauri provides a polished, native cross-platform shell.
- Python provides the strongest ecosystem for GitHub clients, model providers, embeddings, tree-sitter, evaluation, and existing workflow extraction.
- The installer bundles the required Python runtime; users do not install Python manually.
- The background engine is version-matched with the desktop client and updated atomically.

A pure Rust rewrite is rejected for the first product because it delays core workflow correctness without improving model quality or enforcement. A pure Python desktop is rejected because it limits the desired polished product experience.

## Installation and onboarding

One signed installer:

1. Installs Kronos Desktop and the background service.
2. Creates platform-specific data, cache, log, and credential locations.
3. Detects supported local tools and endpoints, including Cursor CLI, OpenCode, Ollama, LM Studio, Docker, Git, and GitHub CLI.
4. Lets the user select or configure planning, coding, reviewing, embedding, and fallback providers.
5. Guides creation and installation of the controller and reviewer GitHub Apps.
6. Stores credentials outside repositories using the OS credential store or isolated service secret mounts.
7. Connects a Telegram bot and restricts it to approved user/chat IDs.
8. Allows repositories to be added through a folder picker or detected git repository list.

GitHub CLI may assist setup but is not a runtime dependency. Runtime GitHub operations use short-lived GitHub App installation tokens.

## Global and repository-local data

### Global application data

Kronos stores outside repositories:

- application settings and repository registry;
- SQLite control/event database;
- one isolated index namespace per repository and commit;
- model and embedding caches;
- disposable task worktrees;
- logs, traces, metrics, budgets, leases, and dead letters;
- global approved skills and imported skill bundles;
- encrypted or access-controlled credentials.

### Committed repository files

Enabling Kronos in a repository proposes a small reviewed change:

- `.kronos/config.yaml`;
- `.github/workflows/kronos-pr.yml`;
- `.github/CODEOWNERS` additions for Kronos policy/workflows;
- optional `.kronos/skills/` files for proven repository-specific procedures.

The repository contains no engine code, vector database, credentials, raw traces, runtime worktrees, or model cache.

Repository policy must be committed because GitHub CI, collaborators, fresh machines, and the independent reviewer need the same versioned rules. Hidden machine-local policy would not be auditable.

## Multi-repository behavior

One Kronos installation registers many repositories and shows them in a global dashboard. Every repository has separate:

- configuration;
- index;
- goals and tasks;
- worktrees;
- budgets and WIP;
- memories and learned skills;
- GitHub installation scope.

A goal targets exactly one repository by default. Models receive no other repository's code. Future workspace groups may enable explicit cross-repository goals, such as a coordinated API and frontend change, but cross-repository retrieval and writes are opt-in and visibly scoped.

## Enabling a repository

The **Enable Kronos** action:

1. Detects repository root, remote, default branch, languages, package managers, likely setup/test/lint/build commands, and existing GitHub workflows.
2. Asks the user to confirm the integration branch, protected branch, commands, risk rules, autonomy, budgets, paths, and executor profile.
3. Shows an exact diff of files it proposes to add or update.
4. Registers the repository globally.
5. Creates its isolated local index.
6. Installs or verifies GitHub Apps and rulesets.
7. Runs a read-only doctor check and a dry-run goal.

The generated config is a starting point, never silently committed or pushed.

## Model routing

Kronos routes roles explicitly:

- deterministic mechanics use no model;
- planning/orchestration uses a cheap or local model;
- coding uses the selected executor;
- independent semantic review may use a separate model;
- embeddings use a local retrieval model.

Users may create global profiles and override them per repository. Kronos records provider, model, version, limits, and outcome for every run. It never silently falls back to an unapproved or paid model.

For the initial Klikday profile:

- orchestration may use an approved free OpenCode model;
- coding may use Cursor CLI;
- retrieval uses Kronos's local index;
- deterministic tests plus the isolated reviewer control integration merges.

Other users can replace Cursor with OpenHands or an OpenAI-compatible local coder without changing the control plane.

## Skills

Kronos supports the portable Agent Skills `SKILL.md` structure and progressive disclosure. It ships a curated, tested engineering set rather than loading a large unrelated catalog into every prompt.

Initial core categories include repository inspection, planning, TDD, debugging, code review, security review, Git/GitHub, dependency changes, migrations, frontend/backend testing, accessibility, documentation, research/citations, and skill regression evaluation.

Community Hermes/Agentskills-compatible skills may be imported through an explicit workflow:

1. Fetch an immutable revision.
2. Scan all included scripts/assets.
3. Display declared capabilities and files.
4. Install into quarantine.
5. Run regression prompts and permission checks.
6. Activate only after approval.

Only relevant skill summaries are exposed during routing; full instructions are loaded when selected. Skill count is not a quality metric.

## Code indexing and context

Each repository has an independent hybrid index:

- SQLite FTS5/BM25 for exact paths, symbols, identifiers, and errors;
- local code embeddings for semantic similarity;
- tree-sitter symbol, import, definition, reference, and test relationships;
- Reciprocal Rank Fusion to combine sparse and dense ranks;
- optional reranking of a small shortlist;
- token-budgeted context assembly with paths, lines, commit hashes, and trust labels.

All-MiniLM-L6-v2 may index English issues and documentation, but a code-trained model is used for source code. Model downloads are pinned, checksum-verified, licensed, and cached locally. Sparse/graph retrieval remains available if dense retrieval is degraded.

The index is not the source of truth. It can always be rebuilt from git and human-readable memory records.

## Goal-to-merge flow

1. A goal enters through Desktop, Telegram, CLI, GitHub, or a schedule.
2. Deterministic policy checks repository scope, freeze, budget, risk, and permissions.
3. A planner produces a schema-valid bounded task graph.
4. Kronos verifies evidence against the indexed commit and creates/deduplicates GitHub issues where configured.
5. A task is claimed transactionally and receives one isolated worktree.
6. Kronos retrieves relevant code, tests, policy, and verified lessons.
7. The selected executor writes a reproduction/failing test and then the implementation.
8. Kronos runs configured checks and bounded repair attempts.
9. The controller App opens a draft PR to the integration branch.
10. Repository CI and the isolated reviewer validate the exact head commit.
11. Eligible work merges automatically into the bot integration branch.
12. Kronos records outcomes and proposes evidence-backed lessons or skills.
13. Promotion to the protected default branch remains a human-reviewed PR in v1.

## Telegram

Telegram is a first-party connector, not a separate agent runtime. It supports:

- creating a goal for a selected repository;
- viewing goals, tasks, failures, budgets, and PR links;
- pausing or resuming allowed work;
- approving explicitly human-gated operations;
- receiving test, review, merge, breaker, and security alerts;
- receiving generated artifacts and reports.

The Telegram connector calls the same engine application services as Desktop. Telegram messages never receive raw GitHub or reviewer credentials.

## Memory and learning

Kronos separates:

- working context for the current task;
- episodic records of runs and outcomes;
- semantic repository/document/issue knowledge;
- procedural lesson and skill candidates;
- immutable policy.

Readable structured records remain authoritative. Embeddings are derived search data. Lessons require source commits, tests/checks, confidence, helpful/harmful outcomes, and rollback links.

Repository-specific skills can be proposed automatically but activate only after configured evidence and regression gates. Global skills and security policy require human approval. A reverted or harmful change disables implicated learning and opens an audit task.

Kronos never stores raw hidden chain-of-thought or secrets as memory.

## Safety and quality

- GitHub controller and reviewer are separate Apps.
- Required checks bind to the reviewer App identity and exact head SHA.
- Default branch direct pushes and autonomous merges are forbidden.
- Workers run in secret-free, resource-limited, network-restricted sandboxes.
- Untrusted issues, code, web results, logs, and imported skills are treated as data.
- File writes are limited to the task worktree and validated against traversal/symlink escapes.
- Every external write is idempotent and auditable.
- Attempts, time, tokens, WIP, concurrency, and cost are bounded.
- Repeated failures trip a circuit breaker rather than spawning indefinitely.
- Kronos cannot silently change protected policy, credentials, required checks, or its autonomy level.

## Success criteria

The standalone design succeeds when:

- a new user installs one application without manually installing Python or Hermes;
- onboarding connects GitHub, Telegram, models, and a repository through guided screens;
- multiple repositories remain isolated while appearing in one dashboard;
- a goal can reach a tested draft PR and eligible integration-branch merge without continuous human input;
- workers and models are replaceable through stable adapters;
- the coding worker cannot issue its own reviewer check;
- indexes and learning improve context without becoming opaque sources of truth;
- failures pause, explain themselves, and recover without duplicate external writes;
- Klikday can migrate from embedded scripts to only committed Kronos policy/workflows.

## Deferred scope

- Autonomous promotion to production/default branches.
- General personal-assistant capabilities unrelated to engineering.
- A Cursor-style full IDE and autocomplete system.
- Unrestricted cross-repository context.
- Training foundation models.
- A large uncurated skill marketplace.
- Hermes dependency or required compatibility.

