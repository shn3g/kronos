# SPDX-License-Identifier: AGPL-3.0-or-later
"""Engine process entrypoint."""

from __future__ import annotations

import socket

import uvicorn

from kronos_engine.api.app import create_app
from kronos_engine.config.settings import load_settings
from kronos_engine.observability.logging import configure_logging
from kronos_engine.state.database import Database


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
    database = Database(settings.paths.database)
    configure_logging(settings.paths.logs)
    sock = _bind_loopback(settings.bind_host, settings.bind_port)
    host, port = sock.getsockname()[:2]
    ready_url = f"http://[{host}]:{port}" if ":" in str(host) else f"http://{host}:{port}"
    app = create_app(settings, database, telegram_auto_poll=True)
    config = uvicorn.Config(app, host=host, port=port, log_config=None)
    server = _ReadyServer(config, ready_url)
    server.run(sockets=[sock])


def _bind_loopback(host: str, port: int) -> socket.socket:
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    if family == socket.AF_INET6:
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.listen()
    return sock


class _ReadyServer(uvicorn.Server):
    def __init__(self, config: uvicorn.Config, ready_url: str) -> None:
        super().__init__(config)
        self._ready_url = ready_url

    async def startup(self, sockets: list[socket.socket] | None = None) -> None:
        await super().startup(sockets=sockets)
        if not self.should_exit:
            print(f"KRONOS_READY {self._ready_url}", flush=True)


if __name__ == "__main__":
    main()
