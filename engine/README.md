# kronos-engine

Local Kronos control-plane. FastAPI is the HTTP composition root. Domain types have no I/O. SQLite WAL stores events, the outbox, leases, and empty repository/goal catalogs.

## Run

```text
python -m kronos_engine
```

Binds `127.0.0.1` only. Set `KRONOS_AUTH_TOKEN` or let the process create `install.json` under the config root. Override roots with `KRONOS_DATA_HOME`, `KRONOS_CONFIG_HOME`, `KRONOS_CACHE_HOME`, and `KRONOS_LOG_HOME`. Worktrees live under the cache root, never in an enrolled git tree.

Authenticated routes: `/health`, `/version`, `/repositories`, `/goals`, `/events`.

## Tests

```text
python -m pytest
python -m ruff check src tests
python -m mypy
```

Hermes is not a dependency.
