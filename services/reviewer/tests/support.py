# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fakes for the isolated reviewer process tests."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from kronos_engine.adapters.github.client import HttpRequest, HttpResponse

POLICY_PATH = ".kronos/config.yaml"
HEAD_SHA = "c" * 40
BASE_SHA = "b" * 40
REVIEWER_APP_ID = 1002


def rsa_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


def policy_mapping(
    *,
    freeze: bool = True,
    risk: str = "high",
    test: Sequence[str] = ("pytest", "-q"),
    locked: Sequence[str] = ("engine/src/kronos_engine/domain/",),
    integration: str = "integration",
    protected: str = "main",
) -> dict[str, object]:
    return {
        "schema_version": 2,
        "branches": {"integration": integration, "protected": protected},
        "commands": {
            "setup": [],
            "test": list(test),
            "lint": [],
            "build": [],
        },
        "autonomy": {"freeze": freeze, "invent_issues": False, "refill_enabled": False},
        "paths": {"locked_prefixes": list(locked)},
        "risk": {"floor": risk},
        "budgets": {
            "max_attempts_per_issue": 3,
            "max_dispatches_per_day": 12,
            "breaker_failure_limit": 4,
            "dry_run_meters": False,
        },
        "wip": {"ready": 2, "running": 3},
        "executor": {"profile": "standard", "sandbox": "default"},
        "indexing": {
            "enabled": True,
            "exclude_prefixes": [
                "node_modules/",
                "vendor/",
                "dist/",
                "build/",
                "target/",
                "__pycache__/",
            ],
            "max_file_bytes": 1048576,
        },
    }


def emit_yaml(value: object, indent: int = 0) -> str:
    if isinstance(value, dict):
        lines: list[str] = []
        for key, item in value.items():
            prefix = "  " * indent + str(key)
            if isinstance(item, dict):
                lines.append(f"{prefix}:")
                lines.append(emit_yaml(item, indent + 1))
            elif isinstance(item, list):
                if not item:
                    lines.append(f"{prefix}: []")
                else:
                    lines.append(f"{prefix}:")
                    lines.append(emit_yaml(item, indent + 1))
            else:
                lines.append(f"{prefix}: {_scalar(item)}")
        return "\n".join(lines)
    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, (dict, list)):
                lines.append("  " * indent + "-")
                lines.append(emit_yaml(item, indent + 1))
            else:
                lines.append("  " * indent + "- " + _scalar(item))
        return "\n".join(lines)
    return "  " * indent + _scalar(value)


def _scalar(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    text = str(value)
    if text == "" or text[:1] in "-?:" or any(ch.isspace() for ch in text) or ":" in text:
        return '"' + text.replace('"', '\\"') + '"'
    return text


class MemorySecrets:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def put(self, name: str, value: str) -> None:
        self.values[name] = value

    def get(self, name: str) -> str | None:
        return self.values.get(name)

    def delete(self, name: str) -> None:
        self.values.pop(name, None)


class RecordingTransport:
    def __init__(self, *, token: str = "ghs_fixture_reviewer") -> None:
        self.token = token
        self.requests: list[HttpRequest] = []

    def send(self, request: HttpRequest) -> HttpResponse:
        self.requests.append(request)
        path = request.url.split("?", 1)[0]
        if request.method.upper() == "POST" and path.endswith("/access_tokens"):
            body = {"token": self.token, "expires_at": "2099-01-01T00:00:00Z"}
            return HttpResponse(200, {}, json.dumps(body).encode())
        if request.method.upper() == "POST" and path.endswith("/check-runs"):
            payload = json.loads(request.body.decode() if request.body else "{}")
            payload["id"] = 1
            payload.setdefault("app", {"id": REVIEWER_APP_ID, "slug": "kronos-reviewer"})
            return HttpResponse(201, {}, json.dumps(payload).encode())
        if request.method.upper() in {"POST", "PUT", "PATCH"} and (
            "/git/" in path or path.endswith("/merge") or "/refs" in path
        ):
            return HttpResponse(403, {}, b'{"message":"reviewer cannot push or merge"}')
        return HttpResponse(200, {}, b"{}")


@dataclass
class FakeGit:
    files: dict[str, dict[str, str]] = field(default_factory=dict)
    reads: list[tuple[str, str]] = field(default_factory=list)
    fetched: list[str] = field(default_factory=list)
    pushed: list[str] = field(default_factory=list)
    diffs: dict[tuple[str, str], tuple[str, ...]] = field(default_factory=dict)

    def add(self, sha: str, path: str, content: str) -> None:
        self.files.setdefault(sha, {})[path] = content

    def add_policy(self, sha: str, raw: Mapping[str, object]) -> None:
        self.add(sha, POLICY_PATH, emit_yaml(dict(raw)) + "\n")

    def fetch_sha(self, sha: str) -> None:
        self.fetched.append(sha)

    def show_file(self, sha: str, path: str) -> str:
        self.reads.append((path, sha))
        return self.files[sha][path]

    def changed_files(self, base_sha: str, head_sha: str) -> tuple[str, ...]:
        return self.diffs.get((base_sha, head_sha), ())

    def export_tree(self, sha: str, dest: Path) -> None:
        dest.mkdir(parents=True, exist_ok=True)
        for relative, content in self.files.get(sha, {}).items():
            target = dest / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

    def push(self, ref: str) -> None:
        self.pushed.append(ref)
        raise RuntimeError("git push is forbidden in tests unless the reviewer blocks it first")


@dataclass
class FakeRunner:
    exit_codes: dict[tuple[str, ...], int] = field(default_factory=dict)
    runs: list[tuple[tuple[str, ...], str]] = field(default_factory=list)
    _issued: int = 0
    reuse: bool = False

    def start_fresh(self) -> str:
        self._issued += 1
        return f"sandbox-{self._issued}"

    def run(
        self, argv: Sequence[str], *, worktree: Path, sandbox_id: str
    ) -> dict[str, Any]:
        command = tuple(argv)
        self.runs.append((command, sandbox_id))
        return {
            "argv": list(command),
            "exit_code": self.exit_codes.get(command, 0),
            "sandbox_fresh": not self.reuse and sandbox_id.startswith("sandbox-"),
        }
