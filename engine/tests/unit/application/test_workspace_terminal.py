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
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "aws-secret-access-key")
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY", "github-app-private-key")

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
            "print(os.environ.get('OPENAI_API_KEY', ''))\n"
            "print(os.environ.get('AWS_SECRET_ACCESS_KEY', ''))\n"
            "print(os.environ.get('GITHUB_APP_PRIVATE_KEY', ''))\n",
        ),
    )
    assert leaked["exit_code"] == 0
    assert "secret-token-value" not in leaked["output"]
    assert "sk-test-key" not in leaked["output"]
    assert "aws-secret-access-key" not in leaked["output"]
    assert "github-app-private-key" not in leaked["output"]


def test_run_workspace_command_times_out(tmp_path: Path) -> None:
    repo = init_git_repo(tmp_path / "alpha", files={"README.md": "hello\n"})

    result = run_workspace_command(
        repo,
        _python_script(repo, "sleep.py", "import time\ntime.sleep(5)\n"),
        timeout_seconds=0.2,
    )

    assert result["timed_out"] is True
    assert result["exit_code"] is None
    assert result["cancelled"] is False


def test_run_workspace_command_stops_when_cancelled(tmp_path: Path) -> None:
    import threading
    import time

    from kronos_engine.application.workspace_terminal import cancel_workspace_command

    repo = init_git_repo(tmp_path / "alpha", files={"README.md": "hello\n"})
    started = repo / "started.txt"
    command = _python_script(
        repo,
        "sleep.py",
        "from pathlib import Path\nimport time\n"
        "Path('started.txt').write_text('1')\ntime.sleep(8)\n",
    )
    run_key = "terminal:repo_alpha"

    def stop_after_start() -> None:
        for _ in range(80):
            if started.exists():
                assert cancel_workspace_command(run_key) is True
                return
            time.sleep(0.05)
        raise AssertionError("command did not start")

    stopper = threading.Thread(target=stop_after_start)
    stopper.start()
    began = time.monotonic()
    result = run_workspace_command(repo, command, run_key=run_key, timeout_seconds=6)
    stopper.join(timeout=2)

    assert result["cancelled"] is True
    assert result["timed_out"] is False
    assert time.monotonic() - began < 4
    assert cancel_workspace_command(run_key) is False


def test_peek_sees_output_while_command_still_runs(tmp_path: Path) -> None:
    import threading
    import time

    from kronos_engine.application.workspace_terminal import peek_workspace_command

    repo = init_git_repo(tmp_path / "alpha", files={"README.md": "hello\n"})
    command = _python_script(
        repo,
        "stream.py",
        "import time\nprint('hello-live', flush=True)\n"
        "time.sleep(3)\nprint('done-live', flush=True)\n",
    )
    run_key = "terminal:repo_stream"
    result_box: dict[str, object] = {}

    def run() -> None:
        result_box["result"] = run_workspace_command(
            repo, command, run_key=run_key, timeout_seconds=8
        )

    worker = threading.Thread(target=run)
    worker.start()
    seen = ""
    deadline = time.monotonic() + 4
    while time.monotonic() < deadline:
        snapshot = peek_workspace_command(run_key)
        if snapshot is not None and "hello-live" in snapshot["output"]:
            seen = snapshot["output"]
            assert snapshot["running"] is True
            assert snapshot["command"] == command
            break
        time.sleep(0.05)
    worker.join(timeout=8)

    assert "hello-live" in seen
    assert peek_workspace_command(run_key) is None
    finished = result_box["result"]
    assert isinstance(finished, dict)
    assert "done-live" in finished["output"]
    assert finished["running"] is False


def test_peek_returns_none_when_nothing_is_running() -> None:
    from kronos_engine.application.workspace_terminal import peek_workspace_command

    assert peek_workspace_command("terminal:missing") is None


def test_kill_process_tree_uses_taskkill_when_sys_platform_is_win32(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """mypy on Windows only hides os.killpg / SIGKILL behind sys.platform, not os.name."""
    import subprocess
    from types import SimpleNamespace

    from kronos_engine.application import workspace_terminal as wt

    calls: list[list[str]] = []

    def fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(list(args))
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(wt.subprocess, "run", fake_run)
    process = SimpleNamespace(pid=4242, poll=lambda: None, kill=lambda: None)

    wt._kill_process_tree(process)  # type: ignore[arg-type]

    assert calls == [["taskkill", "/F", "/T", "/PID", "4242"]]
