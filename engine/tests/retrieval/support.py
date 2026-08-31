# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import subprocess
from pathlib import Path

from tests.support.git_fixtures import init_git_repo

from kronos_engine.config.paths import KronosPaths, resolve_paths
from kronos_engine.domain.policy import default_policy

TINY_EMBED_ONNX = Path(__file__).resolve().parent / "fixtures" / "tiny_embed.onnx"


def write_tiny_embedding_onnx(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(TINY_EMBED_ONNX.read_bytes())
    return path


def kronos_paths(tmp_path: Path) -> KronosPaths:
    paths = resolve_paths(
        environ={
            "KRONOS_DATA_HOME": str(tmp_path / "data"),
            "KRONOS_CONFIG_HOME": str(tmp_path / "config"),
            "KRONOS_CACHE_HOME": str(tmp_path / "cache"),
            "KRONOS_LOG_HOME": str(tmp_path / "logs"),
        }
    )
    for directory in (paths.data, paths.config, paths.cache, paths.logs):
        directory.mkdir(parents=True, exist_ok=True)
    return paths


def indexing_policy():
    return default_policy(integration_branch="main", protected_branch="main")


def git_head(root: Path) -> str:
    return _git(root, "rev-parse", "HEAD").strip()


def commit_tree(root: Path, message: str) -> str:
    _git(root, "add", "-A")
    _git(root, "commit", "--allow-empty", "-m", message)
    return git_head(root)


def write_and_commit(root: Path, files: dict[str, str], message: str) -> str:
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return commit_tree(root, message)


def delete_and_commit(root: Path, relative: str, message: str) -> str:
    _git(root, "rm", "-f", "--", relative.replace("\\", "/"))
    return commit_tree(root, message)


def rename_and_commit(root: Path, src: str, dst: str, message: str) -> str:
    _git(root, "mv", "--", src, dst)
    return commit_tree(root, message)


def golden_fixture(root: Path) -> Path:
    files = {
        ".gitignore": "ignored.txt\n",
        "pkg/__init__.py": "",
        "pkg/db.py": (
            "def connect(dsn: str) -> str:\n"
            "    if not dsn:\n"
            "        raise ValueError('dsn')\n"
            "    return dsn\n"
        ),
        "pkg/api.py": (
            "from pkg.db import connect\n"
            "\n"
            "def handle_request(dsn: str) -> str:\n"
            "    return connect(dsn)\n"
        ),
        "tests/test_db.py": (
            "from pkg import harness\n"
            "\n"
            "def test_open_database_rejects_empty_dsn() -> None:\n"
            "    assert harness.ping() is False\n"
        ),
        "pkg/harness.py": "def ping() -> bool:\n    return False\n",
        "docs/overview.md": (
            "Operators enrol a workspace. Kronos then builds an isolated index.\n"
        ),
        "web/client.ts": (
            "export function fetchSession(id: string): Promise<string> {\n"
            "  return Promise.resolve(id);\n"
            "}\n"
        ),
        "web/app.js": "function renderShell() {\n  return 'ok';\n}\n",
        "vendor/jquery.min.js": "function ignoredVendor() { return 1; }\n",
        "node_modules/leftpad/index.js": "module.exports = function pad() { return ''; }\n",
        "secrets.env": (
            "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE\n"
            "TOKEN=ghp_exampletokenvalueexampletoken12\n"
        ),
        "ignored.txt": "SHOULD_NOT_BE_INDEXED_TOKEN\n",
    }
    init_git_repo(root, files=files, origin="https://github.com/acme/golden.git")
    (root / "binary.bin").write_bytes(b"\x00\x01\x02\xff" * 32)
    (root / "huge.txt").write_text("x" * 2_000_000, encoding="utf-8")
    commit_tree(root, "add skipped artefacts")
    return root


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
        text=True,
        shell=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {args} failed: {result.stderr}")
    return result.stdout
