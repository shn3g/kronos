# kronos-engine

Local Kronos control-plane. FastAPI is the HTTP composition root. Domain types have no I/O. SQLite WAL stores events, the outbox, leases, enrolled repositories, and model profile assignments. Secrets are stored separately from provider configuration.

Authenticated routes: `/health`, `/version`, `/repositories` (list, inspect, enrol, pause, disable, remove, re-enrol, preview), `/models` (detect, register providers, assign roles), `/goals`, `/events`. Enrolment never commits, pushes, or writes `.kronos/` into the working tree. Completions never silently fall back to an unapproved or paid model.

## Run

```text
python -m kronos_engine
```

Binds `127.0.0.1` only. Set `KRONOS_AUTH_TOKEN` or let the process create `install.json` under the config root. Override roots with `KRONOS_DATA_HOME`, `KRONOS_CONFIG_HOME`, `KRONOS_CACHE_HOME`, and `KRONOS_LOG_HOME`. Worktrees live under the cache root, never in an enrolled git tree.

## Tests

```text
python -m pytest
python -m ruff check src tests
python -m mypy
```

Hermes is not a dependency.
