# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from tests.support.git_fixtures import init_git_repo

from kronos_engine.application.workspace_terminal import run_workspace_command


def _python_script(root: Path, name: str, source: str) -> str:
    (root / name).write_text(source, encoding="utf-8")
    return f'"{sys.executable}" {name}'


def test_run_workspace_command_uses_repo_cwd_and_captures_output(tmp_path: Path) -> None:
    repo = init_git_repo(tmp_path / "alpha", files={"marker.txt": "from-workspace\n"})
    command = _python_script(
        repo,
        "probe.py",
        "from pathlib import Path\nprint(Path('marker.txt').read_text())\n",
    )

    result = run_workspace_command(repo, command)

    assert result["exit_code"] == 0
    assert result["timed_out"] is False
    assert "from-workspace" in result["output"]


def test_run_workspace_command_rejects_blank_command(tmp_path: Path) -> None:
    repo = init_git_repo(tmp_path / "alpha", files={"README.md": "hello\n"})

    with pytest.raises(ValueError, match="command"):
        run_workspace_command(repo, "   ")


def test_run_workspace_command_keeps_nonzero_exit_and_strips_engine_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = init_git_repo(tmp_path / "alpha", files={"README.md": "hello\n"})
    monkeypatch.setenv("KRONOS_ENGINE_TOKEN", "secret-token-value")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")

    failed = run_workspace_command(
        repo,
        _python_script(repo, "fail.py", "raise SystemExit(3)\n"),
    )
    assert failed["exit_code"] == 3
    assert failed["timed_out"] is False

    leaked = run_workspace_command(
        repo,
        _python_script(
            repo,
            "env.py",
            "import os\nprint(os.environ.get('KRONOS_ENGINE_TOKEN', ''))\n"
            "print(os.environ.get('OPENAI_API_KEY', ''))\n",
        ),
    )
    assert leaked["exit_code"] == 0
    assert "secret-token-value" not in leaked["output"]
    assert "sk-test-key" not in leaked["output"]


def test_run_workspace_command_times_out(tmp_path: Path) -> None:
    repo = init_git_repo(tmp_path / "alpha", files={"README.md": "hello\n"})

    result = run_workspace_command(
        repo,
        _python_script(repo, "sleep.py", "import time\ntime.sleep(5)\n"),
        timeout_seconds=0.2,
    )

    assert result["timed_out"] is True
    assert result["exit_code"] is None
