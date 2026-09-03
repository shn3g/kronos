# Kronos 0.7.0 Plain-English UX and Engine Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Kronos 0.7.0 read and behave like a Cursor/Hermes-class agentic coding chat: one clean first-run screen, plain-English settings with a uniform form grid, no jargon (no "OpenAI-compatible", "billed", "cost ceiling", "risk ceiling", "sparse/dense/graph", "manifest code", "disabled candidates"), a real gear icon, menus that close on click-outside, goals driven from chat only, and an engine that never hangs on the credential store, never answers a bare `500`, and shows crash details when it dies.

**Architecture:** Desktop (React 19 + Vite + Tauri 2) gets one shared form system (`components/Field.tsx`, `styles/forms.css`) and a reusable `ConnectModelForm` used by both the first-run gate and Settings → Models. Jargon pages (Index, Goals workbench, Import pack, Lesson YAML import) are removed or folded into General. Engine (FastAPI) adds a timeout-guarded secret store, a global JSON error handler, `faulthandler`, a supervised-loop guard, and drops the cost-ceiling gate from chat. Tauri exposes the sidecar crash log to the gate.

**Tech Stack:** React 19, TypeScript, Vitest + Testing Library, Tauri 2 (Rust), Python 3.11+ FastAPI, pytest, ruff, mypy.

## Global Constraints

- One branch: `cursor/release-0-7-020f`. PR stays **draft** (CI does not run on drafts). Commit after every task.
- Lockstep version `0.7.0` in all files checked by `python3 scripts/check-version-sync.py`.
- Copy rules (enforced by a test): no em dash `—` anywhere under `apps/desktop/src` (tests excluded); no user-facing words: `OpenAI-compatible`, `orchestrator`, `billed`, `cost ceiling`, `risk ceiling`, `attempt budget`, `manifest`, `candidates`, `sparse`, `dense`, `graph retrieval`, `import pack`. Plain sentences, one line each. Kronos is "Kronos" or "the app", never "engine" in copy.
- Form layout everywhere: `.field` grid, label column `minmax(120px, 30%)`, control column `1fr`, 16px column gap, controls `min-height: 32px`, hint under the control.
- Local checks before each commit: `cd apps/desktop && pnpm test -- --run` (or the targeted file), `pnpm tsc --noEmit` (or `pnpm -F @kronos/desktop typecheck` if defined), `cd engine && PYTHONPATH=src python3 -m pytest -q`, `python3 -m ruff check src tests`, `python3 -m mypy`.
- Do not delete engine API routes (desktop simplification only); dead desktop code and its tests are deleted, not commented out.
- Reference behaviour the user asked for: Cursor / Hermes / OpenClaw chat-first UX. The user's own "dashboard" repo (OpenClaw integration) was not accessible from this environment; do not guess its content.

## Evidence behind the engine tasks (2026-09-03, engine 0.6.0)

- `POST /models/providers` with an API key **hung for 10+ minutes** on a headless Linux box: `keyring.get_keyring()` blocks on D-Bus SecretService and `OsSecretStore` has no timeout (`engine/src/kronos_engine/adapters/secrets/os_store.py:56-62`). Desktop "Connect" spins forever.
- `Request failed (500)` in the title bar is `apps/desktop/src/features/workspaces/client.ts:284`; FastAPI has no global exception handler, so unexpected errors reach the desktop with no `detail`. Models client throws status-only (`apps/desktop/src/features/models/client.ts:214`).
- "Kronos stopped unexpectedly" is `EngineGate.tsx` when the sidecar exits (`engine.rs` `monitor_child`). Logs live in `{app_log_dir}/engine-sidecar.log` and `engine.log` (Windows: `%LOCALAPPDATA%\app.kronos.desktop\logs\`). Nothing in the UI shows them, so the Windows crash cause is unknown; Task 3 fixes that.

---

## File Structure

**Desktop, new**
- `apps/desktop/src/components/Field.tsx` – label/control grid row, hint, error text.
- `apps/desktop/src/components/FormSection.tsx` – titled section with lead sentence.
- `apps/desktop/src/components/Chips.tsx` – single-select chip group.
- `apps/desktop/src/styles/forms.css` – `.field`, `.form-section`, `.chips`, `.btn` variants.
- `apps/desktop/src/features/models/ConnectModelForm.tsx` – provider chips + model + key (+ server URL for Custom); used by gate and Settings.
- `apps/desktop/src/features/models/providers.ts` – provider presets (moved from `shell/connectModel.ts`, no parser).
- `apps/desktop/src/copy.test.ts` – copy lint (em dash, banned words).
- `apps/desktop/src/features/settings/GeneralPage.tsx` – gains "Search index" status + Rebuild (from IndexPage).

**Desktop, modified**
- `shell/ConnectModelGate.tsx`, `shell/App.tsx`, `shell/MenuBar.tsx`, `shell/ActivityBar.tsx`, `shell/routes.ts`, `shell/EngineGate.tsx`, `shell/InspectorDrawer.tsx`
- `features/models/ModelsPage.tsx`, `LocalEmbeddingsCard.tsx`, `features/models/client.ts`
- `features/connections/github/GitHubPage.tsx`, `features/connections/telegram/TelegramPage.tsx`
- `features/memory/MemoryPage.tsx`, `features/skills/SkillsPage.tsx`
- `features/workspaces/client.ts` (error text), `features/health/checks.ts`
- `styles/shell.css` (remove `.wizard__label/.wizard__input`, `.models__field`, `.index-page__*`, goals workbench blocks), `styles/tokens.css` (em dash in comment), `main.tsx` (import forms.css)
- `src-tauri/src/engine.rs`, `src-tauri/src/lib.rs` (new `engine_crash_log` command), `src/engine/client.ts` + `transport.ts` (wrapper)

**Desktop, deleted**
- `shell/connectModel.ts`, `shell/connectModel.test.ts` (one-liner parser)
- `features/index/IndexPage.tsx`, `IndexPage.test.tsx` (status moves to General)
- `features/goals/GoalsWorkbench.tsx`, `GoalsWorkbench.test.tsx`, `GoalCreateWizard.tsx` (+ test if present)

**Engine, modified**
- `adapters/secrets/os_store.py` (timeout), `api/app.py` (exception handler, supervise-loop guard), `main.py` (`faulthandler`), `application/chat.py` (no cost-ceiling gate), `application/model_profiles.py` (billed default ceiling 0 = unlimited)
- tests: `tests/unit/adapters/test_os_store.py` (new), `tests/unit/api/test_errors.py` (new), `tests/unit/application/test_chat.py`, `tests/unit/application/test_component_supervisor.py`

**Release**
- 16 lockstep files (see `scripts/check-version-sync.py` LOCKSTEP), `CHANGELOG.md`, `README.md`, `docs/quickstart.md`, `docs/architecture/desktop-shell.md`.

---

## Copy glossary (use exactly)

| Old | New |
|---|---|
| Connect a model / "Kronos needs one model before it can chat. Type a one-liner like…" | **Connect a model** / "Pick a provider, paste a key, and start chatting. Keys stay in your system keychain." |
| Quick setup one-liner | removed |
| "A coding worker CLI is on this machine…" | removed from gate; Health check "Coding agents on this computer: Cursor Agent" |
| Name (field) | removed (display name = provider label, or "Custom server") |
| API URL | **Server URL** (shown only for Custom; Ollama/LM Studio prefilled and editable under "Advanced") |
| Model id | **Model** (placeholder per provider, e.g. `gpt-4o-mini`) |
| API key (optional for local servers) | **API key** with hint "Not needed for Ollama or LM Studio." |
| "Assign explicit orchestrator, planner, coder, reviewer, and embedding profiles. Kronos never silently falls back…" | "Pick the model Kronos chats with. Change it any time." |
| Embedding backend: OpenAI-compatible (…) | "Search model: MiniLM (on this computer)" / "Search model: {provider} (online)" / "Search model: none yet. Keyword search still works." |
| MiniLM L6 v2 (384d) | **MiniLM** "Small and fast. Recommended." |
| bge-small-en-v1.5 (384d) | **BGE Small** "Slightly better matches. Larger download." |
| Billed checkbox, Cost ceiling | removed |
| Orchestrator / Planner / Coder / Reviewer / Embedding | Chat / Planning / Coding / Review / Search (under "Advanced: per-task models") |
| Sparse, dense, and graph retrieval per enrolled repository | "Search index" status: "Ready. 1,204 files." / "Indexing…" / "Not built yet." + **Rebuild** |
| Controller manifest code / Reviewer manifest code | **Setup code** hint "GitHub shows this code once after you create the app." |
| Lesson YAML / Import as disabled candidates | removed; page shows "What Kronos remembered" list with Remove per item |
| Import pack / Locator / Revision | removed; list shows core skills with on/off; **Add skill from folder** |
| Risk ceiling / Attempt budget | removed from UI |

---

### Task 1: Secret store timeout (engine)

**Files:**
- Modify: `engine/src/kronos_engine/adapters/secrets/os_store.py`
- Test: `engine/tests/unit/adapters/test_os_store.py` (create)

**Interfaces:**
- Produces: `OsSecretStore.set/get/delete` raise `SecretStoreError("The system credential store did not respond. Kronos could not save the key.")` after `KEYRING_TIMEOUT_SECONDS = 5.0`; module-level `_call_with_timeout(fn, *args, timeout=...)`.

- [ ] **Step 1: Write the failing test**

```python
# engine/tests/unit/adapters/test_os_store.py
# SPDX-License-Identifier: AGPL-3.0-or-later
"""OS secret store never blocks the engine when the keyring hangs."""

from __future__ import annotations

import threading
import time

import pytest

from kronos_engine.adapters.secrets import os_store
from kronos_engine.adapters.secrets.os_store import OsSecretStore, SecretStoreError


class _HangingBackend:
    def set_password(self, service: str, username: str, password: str) -> None:
        time.sleep(60)

    def get_password(self, service: str, username: str) -> str | None:
        time.sleep(60)
        return None

    def delete_password(self, service: str, username: str) -> None:
        time.sleep(60)


def test_set_times_out_with_plain_english_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os_store, "KEYRING_TIMEOUT_SECONDS", 0.2)
    store = OsSecretStore(backend=_HangingBackend())
    started = time.monotonic()
    with pytest.raises(SecretStoreError, match="did not respond"):
        store.set("provider:x:api_key", "sk-test")
    assert time.monotonic() - started < 2.0


def test_get_times_out_and_does_not_leak_non_daemon_threads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(os_store, "KEYRING_TIMEOUT_SECONDS", 0.2)
    store = OsSecretStore(backend=_HangingBackend())
    with pytest.raises(SecretStoreError, match="did not respond"):
        store.get("provider:x:api_key")
    assert all(t.daemon for t in threading.enumerate() if t.name.startswith("kronos-keyring"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && PYTHONPATH=src python3 -m pytest tests/unit/adapters/test_os_store.py -q`
Expected: FAIL (hangs 60s or `KEYRING_TIMEOUT_SECONDS` missing). Use `timeout 30` when running if needed.

- [ ] **Step 3: Implement the timeout wrapper**

In `os_store.py` add near the top (after imports):

```python
import threading
from collections.abc import Callable
from typing import Any

KEYRING_TIMEOUT_SECONDS = 5.0
_TIMEOUT_MESSAGE = "The system credential store did not respond. Kronos could not save the key."


def _call_with_timeout(fn: Callable[..., Any], *args: Any) -> Any:
    result: dict[str, Any] = {}

    def run() -> None:
        try:
            result["value"] = fn(*args)
        except BaseException as error:  # noqa: BLE001 - re-raised on the caller thread
            result["error"] = error

    worker = threading.Thread(target=run, daemon=True, name="kronos-keyring")
    worker.start()
    worker.join(KEYRING_TIMEOUT_SECONDS)
    if worker.is_alive():
        raise SecretStoreError(_TIMEOUT_MESSAGE)
    if "error" in result:
        raise result["error"]
    return result.get("value")
```

Then route every backend call through it: `_call_with_timeout(backend.set_password, SERVICE, name, value)`, `_call_with_timeout(backend.get_password, SERVICE, name)`, `_call_with_timeout(backend.delete_password, SERVICE, name)`, and `_call_with_timeout(keyring.get_keyring)` inside `_resolved_backend` when `self._backend is None` (cache the resolved backend on `self._backend` after first success). Keep existing `KeyringError` → `SecretStoreError` mapping.

- [ ] **Step 4: Run tests**

Run: `cd engine && PYTHONPATH=src python3 -m pytest tests/unit/adapters/test_os_store.py tests/unit -q -k "secret or store or model_profiles"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add engine/src/kronos_engine/adapters/secrets/os_store.py engine/tests/unit/adapters/test_os_store.py
git commit -m "fix(engine): time out credential store calls instead of hanging"
```

---

### Task 2: Global JSON error handler, faulthandler, supervise-loop guard, no cost-ceiling gate (engine)

**Files:**
- Modify: `engine/src/kronos_engine/api/app.py` (after `app = FastAPI(...)` ~line 290; `_supervise_loop` ~line 277)
- Modify: `engine/src/kronos_engine/main.py`
- Modify: `engine/src/kronos_engine/application/chat.py` (`_require_orchestrator` ~line 711-729)
- Modify: `engine/src/kronos_engine/application/model_profiles.py` (`DEFAULT_BILLED_LIMITS.cost_ceiling` → `0.0`)
- Test: `engine/tests/unit/api/test_errors.py` (create), `engine/tests/unit/application/test_chat.py`, `engine/tests/unit/application/test_component_supervisor.py`

**Interfaces:**
- Produces: any unhandled exception → HTTP 500 JSON `{"detail": "<ClassName>: <message>"}` (message redacted via `kronos_engine.observability.redaction.redact_text`, clipped to 300 chars). Chat never raises `OrchestratorNotConfigured` for cost ceiling; billed provider with no key still fails closed.

- [ ] **Step 1: Write failing tests**

```python
# engine/tests/unit/api/test_errors.py
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unexpected engine errors reach the desktop as plain JSON detail."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from kronos_engine.api.app import create_app
from kronos_engine.config.settings import load_settings
from kronos_engine.state.database import Database


@pytest.mark.asyncio
async def test_unhandled_exception_returns_json_detail(tmp_path, monkeypatch) -> None:
    env = {
        "KRONOS_DATA_HOME": str(tmp_path / "data"),
        "KRONOS_CONFIG_HOME": str(tmp_path / "config"),
        "KRONOS_CACHE_HOME": str(tmp_path / "cache"),
        "KRONOS_LOG_HOME": str(tmp_path / "logs"),
        "KRONOS_AUTH_TOKEN": "t",
    }
    settings = load_settings(env)
    for path in (settings.paths.data, settings.paths.config, settings.paths.cache, settings.paths.logs):
        path.mkdir(parents=True, exist_ok=True)
    app = create_app(settings, Database(settings.paths.database))

    @app.get("/__boom")
    def boom() -> None:
        raise RuntimeError("sk-secret-1234567890 exploded")

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://t"
    ) as http:
        response = await http.get("/__boom", headers={"Authorization": "Bearer t"})
    assert response.status_code == 500
    body = response.json()
    assert body["detail"].startswith("RuntimeError:")
    assert "sk-secret-1234567890" not in body["detail"]
```

Add to `test_component_supervisor.py`:

```python
def test_supervise_once_survives_a_stop_that_raises() -> None:
    class _Bad:
        alive = False

        def start(self) -> None:
            self.alive = True

        def stop(self) -> None:
            raise RuntimeError("stop failed")

        def is_alive(self) -> bool:
            return self.alive

    bad = _Bad()
    supervisor = ComponentSupervisor(backoff_seconds=0.0)
    supervisor.register("w", start=bad.start, stop=bad.stop, is_alive=bad.is_alive)
    supervisor.start("w")
    bad.alive = False
    supervisor.supervise_once()  # must not raise
    assert supervisor.status("w")[0].restarts == 1
```

In `test_chat.py`, find the test asserting a 409 / `OrchestratorNotConfigured` for **cost ceiling** (search `cost_ceiling=0` with `billed=True` and an api key present) and change its expectation: with a key present the chat completes; keep `test_billed_orchestrator_without_secret_fails_closed` unchanged.

- [ ] **Step 2: Run to verify failures**

Run: `cd engine && PYTHONPATH=src python3 -m pytest tests/unit/api/test_errors.py tests/unit/application/test_component_supervisor.py -q`
Expected: FAIL (500 body is not JSON detail; stop raising propagates).

- [ ] **Step 3: Implement**

`app.py`, right after `app = FastAPI(...)`:

```python
    @app.exception_handler(Exception)
    async def _unhandled_error(request: Request, error: Exception) -> JSONResponse:
        logging.getLogger("kronos.engine").exception(
            "unhandled error on %s %s", request.method, request.url.path
        )
        message = redact_text(str(error))[:300] or "no details"
        return JSONResponse(
            status_code=500,
            content={"detail": f"{type(error).__name__}: {message}"},
        )
```

(import `JSONResponse` from `fastapi.responses` and `redact_text` from `kronos_engine.observability.redaction`.)

`_supervise_loop`:

```python
        def _supervise_loop() -> None:
            log = logging.getLogger("kronos.engine")
            while not stop_supervise.wait(1.0):
                try:
                    supervisor.supervise_once()
                except Exception:  # noqa: BLE001 - supervision must outlive worker bugs
                    log.exception("component supervision tick failed")
```

`component_supervisor.py` `supervise_once`: wrap `component.stop()` in `try/except Exception: pass` before restart.

`main.py`: add `import faulthandler` and `faulthandler.enable()` as the first line of `main()` (native crashes then print a traceback to stderr, which the sidecar captures into `engine-sidecar.log`).

`chat.py` `_require_orchestrator`: delete the `assert_cost_allowed(...)` / `CostCeilingExceeded` block (keep the billed-without-secret check). Remove now-unused imports.

`model_profiles.py`: `DEFAULT_BILLED_LIMITS` `cost_ceiling=0.0` (0 means no ceiling; nothing enforces it in chat anymore).

- [ ] **Step 4: Run engine checks**

Run: `cd engine && PYTHONPATH=src python3 -m pytest -q && python3 -m ruff check src tests && python3 -m mypy`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add engine
git commit -m "fix(engine): JSON error details, faulthandler, supervise guard, drop cost ceiling gate"
```

---

### Task 3: Crash details in the engine gate (Tauri + desktop)

**Files:**
- Modify: `apps/desktop/src-tauri/src/engine.rs` (add command near `pick_repository_folder`), `apps/desktop/src-tauri/src/lib.rs` (register `engine::engine_crash_log`)
- Modify: `apps/desktop/src/engine/client.ts` (export `engineCrashLog(): Promise<string | null>`; browser preview returns `null`)
- Modify: `apps/desktop/src/shell/EngineGate.tsx`, `apps/desktop/src/shell/App.tsx` (pass `crashLog`)
- Test: `apps/desktop/src/shell/EngineGate.test.tsx` (create)

**Interfaces:**
- Produces: Tauri command `engine_crash_log` → last 40 lines of `engine-sidecar.log` followed by last 40 lines of `engine.log` as one string, or empty string when files are missing. `EngineGate` props gain `crashLog?: string | null`.

- [ ] **Step 1: Failing test**

```tsx
// apps/desktop/src/shell/EngineGate.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { EngineGate } from "./EngineGate";

describe("EngineGate", () => {
  it("shows crash details when Kronos stopped and a log is available", () => {
    render(<EngineGate starting={false} crashLog={"Traceback (most recent call last)\nRuntimeError: boom"} />);
    expect(screen.getByText("Kronos stopped unexpectedly")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Show details" })).toBeInTheDocument();
    expect(screen.getByText(/RuntimeError: boom/)).toBeInTheDocument();
  });
});
```

(Adjust the existing `EngineGate` prop names to match the component; keep "Kronos stopped unexpectedly" text.)

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/desktop && pnpm vitest run src/shell/EngineGate.test.tsx`
Expected: FAIL (no crashLog prop / button).

- [ ] **Step 3: Implement**

Rust (engine.rs):

```rust
#[tauri::command]
pub fn engine_crash_log(app: tauri::AppHandle) -> Result<String, String> {
    let logs = app.path().app_log_dir().map_err(|error| error.to_string())?;
    let mut out = String::new();
    for name in ["engine-sidecar.log", "engine.log"] {
        let path = logs.join(name);
        if let Ok(text) = std::fs::read_to_string(&path) {
            let lines: Vec<&str> = text.lines().collect();
            let start = lines.len().saturating_sub(40);
            out.push_str(&format!("== {name} ==\n"));
            out.push_str(&lines[start..].join("\n"));
            out.push('\n');
        }
    }
    Ok(out)
}
```

Register in `lib.rs` `generate_handler![...]`. TypeScript wrapper in `engine/client.ts`: `export async function engineCrashLog(): Promise<string | null>` using the existing invoke helper pattern; return `null` when `window.__TAURI_INTERNALS__` is absent.

`EngineGate.tsx`: when `!starting`, render a `<details className="gate__details">` with `<summary>Show details</summary>` and `<pre>{crashLog}</pre>` when `crashLog` is non-empty, plus a "Copy details" button (`navigator.clipboard.writeText`). Copy above: "Kronos is restarting. If this keeps happening, copy the details below and open an issue."

`App.tsx`: when engine state becomes `Unavailable`, call `engineCrashLog()` and pass result to `EngineGate`.

- [ ] **Step 4: Run tests**

Run: `cd apps/desktop && pnpm vitest run src/shell && cd src-tauri && cargo check 2>&1 | tail -3`
Expected: PASS; cargo check ok (skip if Rust toolchain missing, note it in the commit body).

- [ ] **Step 5: Commit**

```bash
git add apps/desktop
git commit -m "feat(desktop): show sidecar crash details in the engine gate"
```

---

### Task 4: Shared form system and copy lint (desktop)

**Files:**
- Create: `apps/desktop/src/components/Field.tsx`, `FormSection.tsx`, `Chips.tsx`, `apps/desktop/src/styles/forms.css`, `apps/desktop/src/copy.test.ts`, `apps/desktop/src/components/Field.test.tsx`
- Modify: `apps/desktop/src/main.tsx` (import `./styles/forms.css` after `shell.css`), `apps/desktop/src/styles/tokens.css` (replace the em dash in the comment)

**Interfaces:**
- Produces:
  - `Field({ id, label, hint?, error?, children })` renders `<div class="field"><label class="field__label" for=id>` + `<div class="field__control">children + <p class="field__hint">` + `<p class="field__error" role="alert">`.
  - `FormSection({ title, lead?, children, actions? })` renders `<section class="form-section"><h3 class="form-section__title">…`.
  - `Chips<T extends string>({ label, value, options: {id:T,label:string}[], onChange })` renders `<div role="radiogroup" aria-label=label class="chips">` with `<button role="radio" aria-checked class="chip chip--active">`.
  - Buttons: classes `btn`, `btn--primary`, `btn--ghost`, `btn--danger` (in forms.css).

- [ ] **Step 1: Failing tests**

```ts
// apps/desktop/src/copy.test.ts
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const ROOT = join(__dirname);
const BANNED = [
  "\u2014",
  "OpenAI-compatible",
  "orchestrator",
  "billed",
  "cost ceiling",
  "risk ceiling",
  "attempt budget",
  "manifest",
  "candidates",
  "sparse",
  "graph retrieval",
  "Import pack",
];

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) walk(path, out);
    else if (/\.(tsx|ts|css)$/.test(name) && !/\.test\.(tsx|ts)$/.test(name) && !name.endsWith("copy.test.ts")) out.push(path);
  }
  return out;
}

describe("UI copy", () => {
  it("has no em dashes or jargon in user-facing source", () => {
    const offenders: string[] = [];
    for (const file of walk(ROOT)) {
      const text = readFileSync(file, "utf8");
      // strip TypeScript identifiers like `orchestrator:` object keys by only checking string literals and JSX text
      const visible = text.match(/(["'`])(?:(?!\1).)*\1|>[^<{]+</g)?.join("\n") ?? "";
      for (const word of BANNED) {
        if (visible.toLowerCase().includes(word.toLowerCase())) offenders.push(`${file.replace(ROOT, "src")}: ${word}`);
      }
    }
    expect(offenders).toEqual([]);
  });
});
```

```tsx
// apps/desktop/src/components/Field.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Field } from "./Field";

describe("Field", () => {
  it("links label, control, and hint", () => {
    render(
      <Field id="model" label="Model" hint="Example: gpt-4o-mini">
        <input id="model" />
      </Field>,
    );
    expect(screen.getByLabelText("Model")).toBeInTheDocument();
    expect(screen.getByText("Example: gpt-4o-mini")).toHaveClass("field__hint");
  });
});
```

Note: `copy.test.ts` will fail against many files until Tasks 5-11 land. Commit it in this task anyway (it is the spec); keep it failing until Task 12 makes the suite green. Allowed-list nothing.

- [ ] **Step 2: Run** `cd apps/desktop && pnpm vitest run src/components src/copy.test.ts` → FAIL.

- [ ] **Step 3: Implement**

`Field.tsx`:

```tsx
import type { ReactNode } from "react";

interface FieldProps {
  id: string;
  label: string;
  hint?: string;
  error?: string | null;
  children: ReactNode;
}

export function Field({ id, label, hint, error, children }: FieldProps) {
  return (
    <div className="field">
      <label className="field__label" htmlFor={id}>
        {label}
      </label>
      <div className="field__control">
        {children}
        {hint ? <p className="field__hint">{hint}</p> : null}
        {error ? (
          <p className="field__error" role="alert">
            {error}
          </p>
        ) : null}
      </div>
    </div>
  );
}
```

`FormSection.tsx`:

```tsx
import type { ReactNode } from "react";

interface FormSectionProps {
  title: string;
  lead?: string;
  actions?: ReactNode;
  children: ReactNode;
}

export function FormSection({ title, lead, actions, children }: FormSectionProps) {
  return (
    <section className="form-section">
      <header className="form-section__header">
        <div>
          <h3 className="form-section__title">{title}</h3>
          {lead ? <p className="form-section__lead">{lead}</p> : null}
        </div>
        {actions ? <div className="form-section__actions">{actions}</div> : null}
      </header>
      {children}
    </section>
  );
}
```

`Chips.tsx`:

```tsx
interface ChipOption<T extends string> {
  id: T;
  label: string;
}

interface ChipsProps<T extends string> {
  label: string;
  value: T;
  options: readonly ChipOption<T>[];
  onChange: (value: T) => void;
}

export function Chips<T extends string>({ label, value, options, onChange }: ChipsProps<T>) {
  return (
    <div className="chips" role="radiogroup" aria-label={label}>
      {options.map((option) => (
        <button
          key={option.id}
          type="button"
          role="radio"
          aria-checked={option.id === value}
          className={option.id === value ? "chip chip--active" : "chip"}
          onClick={() => onChange(option.id)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
```

`forms.css`:

```css
.field { display: grid; grid-template-columns: minmax(120px, 30%) minmax(0, 1fr); column-gap: 16px; align-items: start; padding: 8px 0; }
.field__label { color: var(--muted); font-size: 13px; line-height: 32px; }
.field__control { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.field__control > input, .field__control > select, .field__control > textarea {
  width: 100%; min-height: 32px; padding: 6px 10px; border-radius: var(--radius); border: 1px solid var(--hairline-strong);
  background: var(--void-raised); color: var(--ink); font: inherit; font-size: 13px;
}
.field__control > input:focus-visible, .field__control > select:focus-visible, .field__control > textarea:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
.field__hint { margin: 0; font-size: 12px; color: var(--muted); }
.field__error { margin: 0; font-size: 12px; color: #ff8a9b; }
.form-section { padding: 20px 0; border-top: 1px solid var(--hairline); }
.form-section:first-of-type { border-top: 0; padding-top: 0; }
.form-section__header { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 8px; }
.form-section__title { margin: 0; font-size: 14px; font-weight: 600; color: var(--ink); }
.form-section__lead { margin: 4px 0 0; font-size: 13px; color: var(--muted); }
.form-section__actions { display: flex; gap: 8px; }
.chips { display: flex; flex-wrap: wrap; gap: 8px; }
.chip { min-height: 30px; padding: 0 12px; border-radius: 999px; border: 1px solid var(--hairline-strong); background: transparent; color: var(--body); font: inherit; font-size: 13px; cursor: pointer; }
.chip--active { background: var(--ink); color: var(--void); border-color: var(--ink); }
.btn { min-height: 32px; padding: 0 14px; border-radius: var(--radius); border: 1px solid var(--hairline-strong); background: var(--void-raised); color: var(--ink); font: inherit; font-size: 13px; cursor: pointer; }
.btn--primary { background: var(--ink); color: var(--void); border-color: var(--ink); }
.btn--ghost { background: transparent; }
.btn--danger { border-color: #ff8a9b; color: #ff8a9b; }
.btn:disabled { opacity: 0.5; cursor: default; }
.form-actions { display: flex; gap: 8px; justify-content: flex-end; padding-top: 12px; }
.status-line { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--body); margin: 0 0 12px; }
.status-line__dot { width: 8px; height: 8px; border-radius: 50%; background: var(--muted); }
.status-line__dot--ok { background: #5ad38a; }
```

Also replace `—` in `tokens.css` comment with `-`.

- [ ] **Step 4: Run** `pnpm vitest run src/components` → PASS (copy test still red, expected).
- [ ] **Step 5: Commit** `git add apps/desktop && git commit -m "feat(desktop): shared Field/FormSection/Chips form system and copy lint"`

---

### Task 5: ConnectModelForm + new first-run gate (desktop)

**Files:**
- Create: `apps/desktop/src/features/models/providers.ts`, `apps/desktop/src/features/models/ConnectModelForm.tsx`, `ConnectModelForm.test.tsx`
- Modify: `apps/desktop/src/shell/ConnectModelGate.tsx`, `ConnectModelGate.test.tsx`, `apps/desktop/src/shell/App.tsx` (remove worker CLI / detected props from gate)
- Delete: `apps/desktop/src/shell/connectModel.ts`, `connectModel.test.ts`

**Interfaces:**
- `providers.ts`:

```ts
export type ProviderId = "openai" | "openrouter" | "opencode-zen" | "ollama" | "lmstudio" | "custom";
export interface ProviderPreset { id: ProviderId; label: string; url: string; model: string; needsKey: boolean; local: boolean; }
export const PROVIDERS: readonly ProviderPreset[] = [
  { id: "openai", label: "OpenAI", url: "https://api.openai.com/v1", model: "gpt-4o-mini", needsKey: true, local: false },
  { id: "openrouter", label: "OpenRouter", url: "https://openrouter.ai/api/v1", model: "openai/gpt-4o-mini", needsKey: true, local: false },
  { id: "opencode-zen", label: "OpenCode Zen", url: "https://opencode.ai/zen/v1", model: "big-pickle", needsKey: true, local: false },
  { id: "ollama", label: "Ollama", url: "http://127.0.0.1:11434/v1", model: "llama3", needsKey: false, local: true },
  { id: "lmstudio", label: "LM Studio", url: "http://127.0.0.1:1234/v1", model: "local-model", needsKey: false, local: true },
  { id: "custom", label: "Custom", url: "", model: "", needsKey: false, local: false },
];
export function draftFromForm(input: { provider: ProviderId; url: string; model: string; apiKey: string }): ProviderDraft
```
  Copy the exact `url`/`model` values from the current `MODEL_URL_PRESETS` in `shell/connectModel.ts` before deleting it. `draftFromForm` returns `ProviderDraft` with `kind: "openai_compatible"`, `displayName: preset.label` (or "Custom server"), `baseUrl`, `billed: !preset.local && provider !== "custom" ? true : !isLoopback(url)`, `apiKey: apiKey || null`, `modelId: model`.
- `ConnectModelForm` props: `{ onSubmit(draft: ProviderDraft): Promise<void>; submitLabel?: string; initial?: Partial<{ provider: ProviderId; url: string; model: string }>; }`. Renders `Chips` (label "Provider"), `Field id="model-id" label="Model"` (placeholder = preset.model), `Field id="model-key" label="API key"` (`type="password"`, hint "Not needed for Ollama or LM Studio." when `!needsKey`, otherwise "Stored in your system keychain."), and for `custom`/local providers `Field id="model-url" label="Server URL"` (for non-custom hosted providers the URL is fixed and not shown). Validation: model required; key required when `needsKey`; URL required for custom. Errors via `Field error`. Submit button `btn btn--primary` text `submitLabel ?? "Connect"`.

- [ ] **Step 1: Failing tests** (`ConnectModelForm.test.tsx`)

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ConnectModelForm } from "./ConnectModelForm";

describe("ConnectModelForm", () => {
  it("submits an OpenAI draft with the typed key and model", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<ConnectModelForm onSubmit={onSubmit} />);
    await userEvent.click(screen.getByRole("radio", { name: "OpenAI" }));
    await userEvent.type(screen.getByLabelText("Model"), "gpt-4o-mini");
    await userEvent.type(screen.getByLabelText("API key"), "sk-test");
    await userEvent.click(screen.getByRole("button", { name: "Connect" }));
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ baseUrl: "https://api.openai.com/v1", modelId: "gpt-4o-mini", apiKey: "sk-test", displayName: "OpenAI" }),
    );
  });

  it("requires a key for hosted providers and not for Ollama", async () => {
    const onSubmit = vi.fn();
    render(<ConnectModelForm onSubmit={onSubmit} />);
    await userEvent.type(screen.getByLabelText("Model"), "gpt-4o-mini");
    await userEvent.click(screen.getByRole("button", { name: "Connect" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Paste an API key.");
    await userEvent.click(screen.getByRole("radio", { name: "Ollama" }));
    expect(screen.getByText("Not needed for Ollama or LM Studio.")).toBeInTheDocument();
  });

  it("shows a Server URL field only for Custom", async () => {
    render(<ConnectModelForm onSubmit={vi.fn()} />);
    expect(screen.queryByLabelText("Server URL")).toBeNull();
    await userEvent.click(screen.getByRole("radio", { name: "Custom" }));
    expect(screen.getByLabelText("Server URL")).toBeInTheDocument();
  });
});
```

Update `ConnectModelGate.test.tsx`: gate renders heading "Connect a model", lead "Pick a provider, paste a key, and start chatting. Keys stay in your system keychain.", no "Quick setup", no worker CLI text, and a successful submit calls `modelsClient.createProvider` + `assignAll` (or whatever the existing client methods are) then `onConnected`.

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** `providers.ts`, `ConnectModelForm.tsx`, rewrite `ConnectModelGate.tsx` to: `<section class="gate">` brand kicker `KRONOS`, `<p class="gate__step">Step 1 of 3</p>`, `<h1>Connect a model</h1>`, lead, `<ConnectModelForm onSubmit={connect} />`. Keep existing engine calls (register provider → assign all five roles) from the old gate. Delete `connectModel.ts` + test; fix imports in `App.tsx`; remove `detected`/worker props.
- [ ] **Step 4: Run** `pnpm vitest run src/shell src/features/models && pnpm tsc --noEmit` → PASS (copy test aside).
- [ ] **Step 5: Commit** `git commit -am "feat(desktop): plain connect-a-model form shared by gate and settings"`

---

### Task 6: Settings → Models rewrite (desktop)

**Files:**
- Modify: `apps/desktop/src/features/models/ModelsPage.tsx`, `ModelsPage.test.tsx`, `LocalEmbeddingsCard.tsx`, `features/models/client.ts` (parse `detail` on errors: throw `new Error(detail ?? \`Request failed (${status})\`)`)
- Modify: `apps/desktop/src/styles/shell.css` (delete `.models__field` and old provider form styles)

**Interfaces:**
- Page structure (all with `FormSection`):
  1. Kicker `SETTINGS`, title `Models`, lead "Pick the model Kronos chats with. Change it any time."
  2. `FormSection title="Chat model"`: `status-line` "Using {displayName}: {modelId}" (or "No model connected yet."), then `<ConnectModelForm submitLabel="Save" />` which registers the provider and assigns all roles (same as gate).
  3. `FormSection title="Search"` lead "Kronos searches your files with a small local model.": `status-line` per glossary ("Search model: MiniLM (on this computer)" etc.); radio list of catalog entries with labels **MiniLM** / **BGE Small** and one-line descriptions from the glossary; buttons Install / Remove; progress text unchanged.
  4. `<details className="form-advanced"><summary>Advanced: per-task models</summary>` with five `Field` selects labeled Chat, Planning, Coding, Review, Search (values = profile ids; saves via existing `PUT /models/assignments`) and the existing Max tokens field. No Billed, no Cost ceiling, no detected tools list, no raw "Create provider" form.
- `LocalEmbeddingsCard` keeps `variant="gate"` for Step 2 but uses the same labels/descriptions; the gate copy: "Install search" / "Kronos needs one small download to search your files. It stays on this computer."

- [ ] **Step 1: Failing tests** in `ModelsPage.test.tsx`: renders lead sentence; renders "Search model: none yet. Keyword search still works." when backend kind `none`; renders "Search model: MiniLM (on this computer)" when backend kind `onnx` and model `minilm-l6-v2`; renders "Search model: OpenCode Zen (online)" when kind `openai_compatible` with display name "OpenCode Zen"; does not render text `Billed` or `Cost ceiling`; error from a failed save shows the engine `detail` string.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4:** `pnpm vitest run src/features/models` → PASS.
- [ ] **Step 5: Commit** `git commit -am "feat(desktop): rewrite Models settings in plain English"`

---

### Task 7: Menu bar click-outside, gear icon, settings sections, Index → General (desktop)

**Files:**
- Modify: `apps/desktop/src/shell/MenuBar.tsx`, `MenuBar.test.tsx`, `ActivityBar.tsx`, `ActivityBar.test.tsx`, `shell/routes.ts`, `routes.test.ts`, `features/settings/SettingsHub.tsx`, `SettingsHub.test.tsx`, `features/settings/GeneralPage.tsx` (+ test)
- Delete: `features/index/IndexPage.tsx`, `IndexPage.test.tsx` (move the status/rebuild client calls into GeneralPage; keep `features/index/client.ts` if other code imports it)

- [ ] **Step 1: Failing tests**
  - `MenuBar.test.tsx`: "closes an open menu when clicking outside" (open File, `fireEvent.mouseDown(document.body)`, expect menu items gone) and "switches menus on hover while one is open".
  - `ActivityBar.test.tsx`: settings button contains an `<svg data-icon="gear">` with a `<circle>` child.
  - `routes.test.ts`: `SETTINGS_SECTIONS` ids equal `["general","models","connections","skills","memory","notifications","updates"]`; legacy `#/index` maps to `settings/general`; `#/goals` maps to `chat`.
  - `GeneralPage.test.tsx`: shows "Search index" line "Ready. 3 files." when the index status reports 3 documents and a **Rebuild** button that calls the rebuild client.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**

MenuBar click-outside:

```tsx
  const rootRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (open === null) return;
    const onDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(null);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);
```

Add `ref={rootRef}` on the `.menu-bar` div and `onMouseEnter={() => open !== null && setOpen(id)}` on each trigger.

ActivityBar gear (glyph adapted from Lucide, ISC):

```tsx
<svg data-icon="gear" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
  <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" />
  <circle cx="12" cy="12" r="3" />
</svg>
```

Routes: remove `index` section; add legacy `"/index"` → general and `"/goals"` → chat (Task 8 removes the activity). SettingsHub: remove Index case. GeneralPage: add `FormSection title="Search index"` with `status-line` and Rebuild button using the existing index client (`features/index/client.ts`).

- [ ] **Step 4: Run** `pnpm vitest run src/shell src/features/settings && pnpm tsc --noEmit` → PASS.
- [ ] **Step 5: Commit** `git commit -am "feat(desktop): gear icon, click-outside menus, index status in General"`

---

### Task 8: Goals move into chat (desktop)

**Files:**
- Modify: `apps/desktop/src/shell/ActivityBar.tsx` (remove `goals` item), `shell/routes.ts` (`ShellActivity` without `goals`), `shell/App.tsx` (remove Goals page route), `shell/InspectorDrawer.tsx` (Goals tab stays: title + state + one-line readiness), `features/chat/ChatPage.tsx` (empty-state hint: "Type /goal followed by what done looks like. Kronos plans, runs the tests, and reports back here.")
- Delete: `features/goals/GoalsWorkbench.tsx`, `GoalsWorkbench.test.tsx`, `features/goals/GoalCreateWizard.tsx` (+ test), any goals-only CSS in `shell.css`
- Tests: `ActivityBar.test.tsx` (4 items: Chat, Files, Workspaces + Settings foot), `App.test.tsx` (no Goals activity), `ChatPage.test.tsx` (hint text)

- [ ] **Step 1: Failing tests** for the three assertions above. **Step 2: Run** → FAIL. **Step 3: Implement** (delete files, fix imports, keep `features/goals/client.ts` used by the inspector). **Step 4:** `pnpm vitest run && pnpm tsc --noEmit` → PASS except `copy.test.ts`.
- [ ] **Step 5: Commit** `git commit -am "feat(desktop): goals live in chat; remove Goals workbench and budgets UI"`

---

### Task 9: Connections in the form grid (desktop)

**Files:**
- Modify: `features/connections/github/GitHubPage.tsx`, `GitHubPage.test.tsx`, `features/connections/telegram/TelegramPage.tsx`, `TelegramPage.test.tsx`, `styles/shell.css` (remove `.wizard__label/.wizard__input` once no usages remain)

- [ ] **Step 1: Failing tests**: GitHubPage shows two `FormSection`s "GitHub app" and "Reviewer app", each with `Field label="Setup code"` (hint "GitHub shows this code once after you create the app.") and `Field label="Installation ID"`; no text "manifest"; the safety list has no em dash. TelegramPage: `FormSection title="Telegram"` lead "Get goal updates and approve steps from your phone."; fields "Bot token file", "Allowed user IDs", "Allowed chat IDs" via `Field`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** with `Field`/`FormSection`; preserve all client calls and behaviour. **Step 4:** `pnpm vitest run src/features/connections` → PASS.
- [ ] **Step 5: Commit** `git commit -am "feat(desktop): connections pages use the shared form grid"`

---

### Task 10: Memory and Skills simplified (desktop)

**Files:**
- Modify: `features/memory/MemoryPage.tsx`, `MemoryPage.test.tsx`, `features/skills/SkillsPage.tsx`, `SkillsPage.test.tsx`, `features/skills/client.ts` (add `importFromFolder(path)` calling existing `POST /skills/import` with a `file://` locator if that is what the engine accepts; check `api/app.py` ~1843-1867)

**Interfaces:**
- MemoryPage: kicker `SETTINGS`, title `Memory`, lead "Kronos remembers lessons from your workspaces here."; list of records (`text`, workspace, date) with a `btn--ghost` "Remove" per row if the client supports delete, otherwise a status badge; empty state "Nothing remembered yet. Lessons appear as Kronos works." No textarea, no import button.
- SkillsPage: title `Skills`, lead "Skills are short instruction packs Kronos follows. Core skills are built in."; list rows: name, one-line description, status pill (Active / Off); section actions: `btn` "Add skill from folder" → `pick_repository_folder` dialog → `importFromFolder`. No Locator/Revision inputs.

- [ ] **Step 1: Failing tests**: MemoryPage renders lead + empty state, no "YAML"; SkillsPage renders core skill names from a mocked `GET /skills` response and a button "Add skill from folder", no "Import pack".
- [ ] **Steps 2-4** as usual. **Step 5:** `git commit -am "feat(desktop): plain Memory and Skills pages"`

---

### Task 11: Health shows coding agents; error banner shows detail (desktop)

**Files:**
- Modify: `features/health/checks.ts` (+ test): add check `id: "agents"`, label "Coding agents", detail "On this computer: Cursor Agent, Claude Code" from `GET /models` `detected[]` (names mapped: `cursor-agent` → Cursor Agent, `claude` → Claude Code, `opencode` → OpenCode), `ok: true` always.
- Modify: `features/workspaces/client.ts` `engineErrorMessage` → when no `detail`: "Kronos could not finish that request (code {status})."; `shell/App.tsx` title-bar error renders the sentence.

- [ ] Steps 1-5 (tests: checks include `agents` line; error text without detail matches new sentence). Commit: `git commit -am "feat(desktop): coding agents in Health; readable request errors"`

---

### Task 12: Sweep, copy lint green, docs, 0.7.0 lockstep

**Files:**
- Modify: remaining offenders reported by `copy.test.ts` (run it and fix each string), `styles/shell.css` (delete dead blocks), `README.md`, `docs/quickstart.md`, `docs/architecture/desktop-shell.md` (Settings sections, no Goals activity, gear, connect form), `CHANGELOG.md` (`## [0.7.0] - <date>` with Added/Changed/Fixed/Removed; compare links), 16 lockstep files → `0.7.0`.

- [ ] **Step 1:** `cd apps/desktop && pnpm vitest run` → `copy.test.ts` lists offenders. Fix each string per glossary until green.
- [ ] **Step 2:** `pnpm tsc --noEmit && pnpm lint` (if defined) → clean. `cd engine && PYTHONPATH=src python3 -m pytest -q && python3 -m ruff check src tests && python3 -m mypy` → clean.
- [ ] **Step 3:** Bump versions with the same replacement approach as the 0.6.0 release commit (`git show 2423859 --stat` lists the 16 files); run `python3 scripts/check-version-sync.py` → no output.
- [ ] **Step 4:** CHANGELOG 0.7.0 entry (plain sentences, no em dashes):
  - Added: crash details in the start screen; JSON error details from the engine; Coding agents line in Health; shared form layout.
  - Changed: Connect a model is one form (provider, model, key); Settings → Models rewritten; Index status moved to General; Connections, Memory, Skills simplified; gear icon; menus close on click outside; goals run from chat.
  - Removed: quick-setup one-liner, Goals workbench and budget fields, Billed and Cost ceiling controls, Lesson YAML import, Import pack form.
  - Fixed: engine no longer hangs when the system credential store does not answer; supervision survives worker errors; chat no longer refuses on a cost ceiling.
- [ ] **Step 5:** `git commit -am "release: 0.7.0"` and push `git push -u origin cursor/release-0-7-020f`; keep PR draft.

---

## Self-Review

- Spec coverage: first-run screen (T5), quick setup removed (T5), worker CLI box removed (T5/T11), Models copy/jargon (T6), MiniLM/BGE descriptions (T6), Custom provider (T5), Billed/cost ceiling removed (T2/T6), settings icon (T7), menu click-outside (T7), Index jargon + search bar removed (T7), Connections layout/labels (T9, T4), em dashes (T4 lint), Memory lessons import removed (T10), Skills import pack removed + preloaded skills visible (T10), Goals UI removed / chat-first (T8), risk ceiling & budgets hidden (T8), engine hang (T1), bare 500 (T2/T11), crash screen with details (T3), version bump + branch/draft policy (T12). Files editor Find/Replace left as is (functional; not in this cut).
- Placeholder scan: every task lists exact files; components have full code; page rewrites specify structure, copy, and test assertions.
- Type consistency: `Field(id,label,hint,error,children)`, `FormSection(title,lead,actions,children)`, `Chips(label,value,options,onChange)`, `ProviderPreset{id,label,url,model,needsKey,local}`, `ConnectModelForm({onSubmit,submitLabel,initial})`, `engineCrashLog(): Promise<string|null>`, `EngineGate crashLog` are used identically across tasks.
