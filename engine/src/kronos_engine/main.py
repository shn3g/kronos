# SPDX-License-Identifier: AGPL-3.0-or-later
"""Engine process entrypoint."""

from __future__ import annotations

import socket

import uvicorn

from kronos_engine.api.app import create_app
from kronos_engine.config.settings import load_settings
from kronos_engine.state.database import connect


def main() -> None:
    settings = load_settings()
    for directory in (
        settings.paths.data,
        settings.paths.config,
        settings.paths.cache,
        settings.paths.logs,
        settings.paths.worktrees,
    ):
        directory.mkdir(parents=True, exist_ok=True)
    conn = connect(settings.paths.database)
    app = create_app(settings, conn)
    port = settings.bind_port if settings.bind_port > 0 else _ephemeral_port()

    @app.on_event("startup")
    def announce_ready() -> None:
        print(f"KRONOS_READY http://{settings.bind_host}:{port}", flush=True)

    uvicorn.run(app, host=settings.bind_host, port=port, log_config=None)


def _ephemeral_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


if __name__ == "__main__":
    main()
