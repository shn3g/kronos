# SPDX-License-Identifier: AGPL-3.0-or-later
"""Workspace HTTP: files, working-tree changes, local commits, and write reverts."""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from tests.support.git_fixtures import init_git_repo
from tests.support.secrets import InMemorySecretStore

from kronos_engine.api.app import create_app
from kronos_engine.config.paths import resolve_paths
from kronos_engine.config.settings import Settings
from kronos_engine.state.database import Database


def _settings(tmp_path: Path) -> Settings:
    paths = resolve_paths(
        environ={
            "KRONOS_DATA_HOME": str(tmp_path / "data"),
            "KRONOS_CONFIG_HOME": str(tmp_path / "config"),
            "KRONOS_CACHE_HOME": str(tmp_path / "cache"),
            "KRONOS_LOG_HOME": str(tmp_path / "logs"),
        }
    )
    return Settings(
        engine_version="0.1.0",
        min_client_version="0.1.0",
        bind_host="127.0.0.1",
        bind_port=0,
        auth_token="install-token",
        paths=paths,
    )


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[tuple[AsyncClient, dict[str, str], Path]]:
    repo = init_git_repo(tmp_path / "alpha", files={"hello.py": "old\n"})
    database = Database(tmp_path / "data" / "kronos.sqlite3")
    app = create_app(_settings(tmp_path), database, secret_store=InMemorySecretStore())
    http = AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.1", 50000)),
        base_url="http://127.0.0.1",
    )
    headers = {"Authorization": "Bearer install-token"}
    try:
        yield http, headers, repo
    finally:
        await http.aclose()


@pytest.mark.asyncio
async def test_working_tree_changes_and_commit_fail_closed(
    client: tuple[AsyncClient, dict[str, str], Path],
) -> None:
    http, headers, repo = client
    enrolled = await http.post("/repositories", headers=headers, json={"path": str(repo)})
    assert enrolled.status_code == 200
    repo_id = enrolled.json()["repository"]["id"]
    (repo / "hello.py").write_text("new\n", encoding="utf-8")
    (repo / "fresh.py").write_text("hi\n", encoding="utf-8")

    unauth = await http.get(f"/repositories/{repo_id}/changes")
    assert unauth.status_code == 401

    listed = await http.get(f"/repositories/{repo_id}/changes", headers=headers)
    assert listed.status_code == 200
    paths = {item["path"]: item for item in listed.json()["changes"]}
    assert "-old" in paths["hello.py"]["patch"]
    assert "+new" in paths["hello.py"]["patch"]
    assert paths["hello.py"]["from_chat"] is False
    assert paths["fresh.py"]["summary"].startswith("Added")
    assert paths["fresh.py"]["from_chat"] is False

    empty = await http.post(
        f"/repositories/{repo_id}/commits",
        headers=headers,
        json={"message": "   "},
    )
    assert empty.status_code == 400

    committed = await http.post(
        f"/repositories/{repo_id}/commits",
        headers=headers,
        json={"message": "Fix hello.py", "paths": ["hello.py", "fresh.py"]},
    )
    assert committed.status_code == 200
    assert committed.json()["ok"] is True
    assert (repo / "hello.py").read_text(encoding="utf-8") == "new\n"

    after = await http.get(f"/repositories/{repo_id}/changes", headers=headers)
    assert after.json()["changes"] == []

    nothing = await http.post(
        f"/repositories/{repo_id}/commits",
        headers=headers,
        json={"message": "Again"},
    )
    assert nothing.status_code == 409


@pytest.mark.asyncio
async def test_workspace_files_list_and_read_fail_closed(
    client: tuple[AsyncClient, dict[str, str], Path],
) -> None:
    http, headers, repo = client
    (repo / "src").mkdir()
    (repo / "src" / "app.py").write_text("print(1)\n", encoding="utf-8")
    enrolled = await http.post("/repositories", headers=headers, json={"path": str(repo)})
    assert enrolled.status_code == 200
    repo_id = enrolled.json()["repository"]["id"]

    unauth = await http.get(f"/repositories/{repo_id}/files")
    assert unauth.status_code == 401

    missing_repo = await http.get("/repositories/repo_missing/files", headers=headers)
    assert missing_repo.status_code == 404

    listed = await http.get(f"/repositories/{repo_id}/files", headers=headers)
    assert listed.status_code == 200
    paths = {item["path"] for item in listed.json()["files"]}
    assert "hello.py" in paths
    assert "src/app.py" in paths

    missing_path = await http.get(
        f"/repositories/{repo_id}/files/contents",
        headers=headers,
    )
    assert missing_path.status_code == 400

    escaped = await http.get(
        f"/repositories/{repo_id}/files/contents",
        headers=headers,
        params={"path": "../secret.txt"},
    )
    assert escaped.status_code == 409

    contents = await http.get(
        f"/repositories/{repo_id}/files/contents",
        headers=headers,
        params={"path": "src/app.py"},
    )
    assert contents.status_code == 200
    payload = contents.json()
    assert payload["path"] == "src/app.py"
    assert payload["content"] == "print(1)\n"
    assert payload["binary"] is False


@pytest.mark.asyncio
async def test_workspace_terminal_run_fail_closed(
    client: tuple[AsyncClient, dict[str, str], Path],
) -> None:
    http, headers, repo = client
    enrolled = await http.post("/repositories", headers=headers, json={"path": str(repo)})
    assert enrolled.status_code == 200
    repo_id = enrolled.json()["repository"]["id"]

    unauth = await http.post(f"/repositories/{repo_id}/terminal/runs", json={"command": "echo hi"})
    assert unauth.status_code == 401

    missing = await http.post(
        "/repositories/repo_missing/terminal/runs",
        headers=headers,
        json={"command": "echo hi"},
    )
    assert missing.status_code == 404

    empty = await http.post(
        f"/repositories/{repo_id}/terminal/runs",
        headers=headers,
        json={"command": "   "},
    )
    assert empty.status_code == 400

    (repo / "probe.py").write_text(
        "from pathlib import Path\nprint(Path('hello.py').read_text())\n",
        encoding="utf-8",
    )
    ran = await http.post(
        f"/repositories/{repo_id}/terminal/runs",
        headers=headers,
        json={"command": f'"{sys.executable}" probe.py'},
    )
    assert ran.status_code == 200
    payload = ran.json()
    assert payload["exit_code"] == 0
    assert payload["timed_out"] is False
    assert payload["cancelled"] is False
    assert "old" in payload["output"]


@pytest.mark.asyncio
async def test_workspace_terminal_cancel_stops_a_running_command(
    client: tuple[AsyncClient, dict[str, str], Path],
) -> None:
    import asyncio

    http, headers, repo = client
    enrolled = await http.post("/repositories", headers=headers, json={"path": str(repo)})
    assert enrolled.status_code == 200
    repo_id = enrolled.json()["repository"]["id"]
    (repo / "sleep.py").write_text(
        "from pathlib import Path\nimport time\n"
        "Path('started.txt').write_text('1')\ntime.sleep(8)\n",
        encoding="utf-8",
    )

    unauth = await http.post(f"/repositories/{repo_id}/terminal/runs/cancel")
    assert unauth.status_code == 401

    missing = await http.post("/repositories/repo_missing/terminal/runs/cancel", headers=headers)
    assert missing.status_code == 404

    idle = await http.post(f"/repositories/{repo_id}/terminal/runs/cancel", headers=headers)
    assert idle.status_code == 200
    assert idle.json()["ok"] is False

    running = asyncio.create_task(
        http.post(
            f"/repositories/{repo_id}/terminal/runs",
            headers=headers,
            json={"command": f'"{sys.executable}" sleep.py'},
            timeout=10,
        )
    )
    started = repo / "started.txt"
    for _ in range(80):
        if started.exists():
            break
        await asyncio.sleep(0.05)
    else:
        running.cancel()
        raise AssertionError("command did not start")

    stopped = await http.post(f"/repositories/{repo_id}/terminal/runs/cancel", headers=headers)
    assert stopped.status_code == 200
    assert stopped.json()["ok"] is True
    ran = await running
    assert ran.status_code == 200
    payload = ran.json()
    assert payload["cancelled"] is True
    assert payload["timed_out"] is False


@pytest.mark.asyncio
async def test_workspace_terminal_peek_streams_output_and_fail_closed(
    client: tuple[AsyncClient, dict[str, str], Path],
) -> None:
    import asyncio

    http, headers, repo = client
    enrolled = await http.post("/repositories", headers=headers, json={"path": str(repo)})
    repo_id = enrolled.json()["repository"]["id"]
    (repo / "stream.py").write_text(
        "import time\nprint('hello-live', flush=True)\n"
        "time.sleep(4)\nprint('done-live', flush=True)\n",
        encoding="utf-8",
    )

    unauth = await http.get(f"/repositories/{repo_id}/terminal/runs")
    assert unauth.status_code == 401

    missing = await http.get("/repositories/repo_missing/terminal/runs", headers=headers)
    assert missing.status_code == 404

    idle = await http.get(f"/repositories/{repo_id}/terminal/runs", headers=headers)
    assert idle.status_code == 200
    assert idle.json()["running"] is False

    running = asyncio.create_task(
        http.post(
            f"/repositories/{repo_id}/terminal/runs",
            headers=headers,
            json={"command": f'"{sys.executable}" stream.py'},
            timeout=10,
        )
    )
    seen = False
    for _ in range(80):
        peeked = await http.get(f"/repositories/{repo_id}/terminal/runs", headers=headers)
        if peeked.status_code == 200 and "hello-live" in peeked.json().get("output", ""):
            assert peeked.json()["running"] is True
            seen = True
            break
        await asyncio.sleep(0.05)
    ran = await running
    assert seen is True
    assert ran.status_code == 200
    assert "done-live" in ran.json()["output"]
    assert ran.json()["running"] is False


@pytest.mark.asyncio
async def test_workspace_terminal_shell_session_fail_closed(
    client: tuple[AsyncClient, dict[str, str], Path],
) -> None:
    import asyncio

    http, headers, repo = client
    enrolled = await http.post("/repositories", headers=headers, json={"path": str(repo)})
    repo_id = enrolled.json()["repository"]["id"]

    unauth = await http.post(f"/repositories/{repo_id}/terminal/sessions")
    assert unauth.status_code == 401

    missing = await http.post("/repositories/repo_missing/terminal/sessions", headers=headers)
    assert missing.status_code == 404

    started = await http.post(f"/repositories/{repo_id}/terminal/sessions", headers=headers)
    assert started.status_code == 200
    assert started.json()["running"] is True
    try:
        unauth_in = await http.post(
            f"/repositories/{repo_id}/terminal/sessions/input",
            json={"line": "echo hello-shell"},
        )
        assert unauth_in.status_code == 401

        first = await http.post(
            f"/repositories/{repo_id}/terminal/sessions/input",
            headers=headers,
            json={"line": "echo hello-shell\n"},
        )
        assert first.status_code == 200
        assert first.json()["ok"] is True

        seen_first = False
        for _ in range(80):
            peeked = await http.get(f"/repositories/{repo_id}/terminal/runs", headers=headers)
            if peeked.status_code == 200 and "hello-shell" in peeked.json().get("output", ""):
                assert peeked.json()["running"] is True
                seen_first = True
                break
            await asyncio.sleep(0.05)
        assert seen_first is True

        second = await http.post(
            f"/repositories/{repo_id}/terminal/sessions/input",
            headers=headers,
            json={"line": "echo second-line\n"},
        )
        assert second.status_code == 200
        seen_second = False
        for _ in range(80):
            peeked = await http.get(f"/repositories/{repo_id}/terminal/runs", headers=headers)
            output = peeked.json().get("output", "")
            if (
                "hello-shell" in output
                and "second-line" in output
                and peeked.json()["running"] is True
            ):
                seen_second = True
                break
            await asyncio.sleep(0.05)
        assert seen_second is True
    finally:
        stopped = await http.post(f"/repositories/{repo_id}/terminal/runs/cancel", headers=headers)
        assert stopped.status_code == 200
        assert stopped.json()["ok"] is True


@pytest.mark.asyncio
async def test_workspace_file_write_fail_closed(
    client: tuple[AsyncClient, dict[str, str], Path],
) -> None:
    http, headers, repo = client
    enrolled = await http.post("/repositories", headers=headers, json={"path": str(repo)})
    assert enrolled.status_code == 200
    repo_id = enrolled.json()["repository"]["id"]

    unauth = await http.put(
        f"/repositories/{repo_id}/files/contents",
        json={"path": "hello.py", "content": "applied\n"},
    )
    assert unauth.status_code == 401

    missing_repo = await http.put(
        "/repositories/repo_missing/files/contents",
        headers=headers,
        json={"path": "hello.py", "content": "applied\n"},
    )
    assert missing_repo.status_code == 404

    empty_path = await http.put(
        f"/repositories/{repo_id}/files/contents",
        headers=headers,
        json={"path": "   ", "content": "applied\n"},
    )
    assert empty_path.status_code == 400

    too_large = await http.put(
        f"/repositories/{repo_id}/files/contents",
        headers=headers,
        json={"path": "hello.py", "content": "x" * 200_001},
    )
    assert too_large.status_code == 400
    assert (repo / "hello.py").read_text(encoding="utf-8") == "old\n"

    escaped = await http.put(
        f"/repositories/{repo_id}/files/contents",
        headers=headers,
        json={"path": "../secret.txt", "content": "nope\n"},
    )
    assert escaped.status_code == 409
    assert (repo / "hello.py").read_text(encoding="utf-8") == "old\n"

    wrote = await http.put(
        f"/repositories/{repo_id}/files/contents",
        headers=headers,
        json={"path": "hello.py", "content": "applied\n"},
    )
    assert wrote.status_code == 200
    assert wrote.json()["ok"] is True
    assert wrote.json()["path"] == "hello.py"
    assert (repo / "hello.py").read_text(encoding="utf-8") == "applied\n"

    listed = await http.get(f"/repositories/{repo_id}/changes", headers=headers)
    by_path = {item["path"]: item for item in listed.json()["changes"]}
    assert by_path["hello.py"]["from_chat"] is True

    events = await http.get("/events", headers=headers)
    wrote_events = [item for item in events.json()["events"] if item["type"] == "git.wrote"]
    assert wrote_events[-1]["payload"]["path"] == "hello.py"
    assert wrote_events[-1]["payload"]["summary"] == "Wrote hello.py"
    assert "+applied" in wrote_events[-1]["payload"]["patch"]


@pytest.mark.asyncio
async def test_workspace_write_refuses_locked_prefixes(
    client: tuple[AsyncClient, dict[str, str], Path],
) -> None:
    http, headers, repo = client
    (repo / "locked").mkdir()
    (repo / "locked" / "keep.py").write_text("keep\n", encoding="utf-8")
    enrolled = await http.post(
        "/repositories",
        headers=headers,
        json={"path": str(repo), "policy": {"paths": {"locked_prefixes": ["locked/"]}}},
    )
    assert enrolled.status_code == 200
    repo_id = enrolled.json()["repository"]["id"]

    refused = await http.put(
        f"/repositories/{repo_id}/files/contents",
        headers=headers,
        json={"path": "locked/keep.py", "content": "changed\n"},
    )
    assert refused.status_code == 409
    assert "locked" in refused.json()["detail"]
    assert (repo / "locked" / "keep.py").read_text(encoding="utf-8") == "keep\n"


@pytest.mark.asyncio
async def test_workspace_write_revert_restores_the_file_and_fails_closed(
    client: tuple[AsyncClient, dict[str, str], Path],
) -> None:
    http, headers, repo = client
    enrolled = await http.post("/repositories", headers=headers, json={"path": str(repo)})
    assert enrolled.status_code == 200
    repo_id = enrolled.json()["repository"]["id"]

    unauth = await http.post(
        f"/repositories/{repo_id}/writes/revert", json={"path": "hello.py"}
    )
    assert unauth.status_code == 401

    missing_repo = await http.post(
        "/repositories/repo_missing/writes/revert",
        headers=headers,
        json={"path": "hello.py"},
    )
    assert missing_repo.status_code == 404

    blank = await http.post(
        f"/repositories/{repo_id}/writes/revert",
        headers=headers,
        json={"path": "   "},
    )
    assert blank.status_code == 400

    wrote = await http.put(
        f"/repositories/{repo_id}/files/contents",
        headers=headers,
        json={"path": "hello.py", "content": "applied\n"},
    )
    assert wrote.status_code == 200

    reverted = await http.post(
        f"/repositories/{repo_id}/writes/revert",
        headers=headers,
        json={"path": "hello.py"},
    )
    assert reverted.status_code == 200
    assert reverted.json()["ok"] is True
    assert (repo / "hello.py").read_text(encoding="utf-8") == "old\n"

    listed = await http.get(f"/repositories/{repo_id}/changes", headers=headers)
    assert listed.json()["changes"] == []

    events = await http.get("/events", headers=headers)
    reverted_events = [item for item in events.json()["events"] if item["type"] == "git.reverted"]
    assert reverted_events[-1]["payload"]["path"] == "hello.py"
    assert reverted_events[-1]["payload"]["summary"] == "Reverted hello.py"


@pytest.mark.asyncio
async def test_commit_forgets_chat_backups_for_committed_paths(
    client: tuple[AsyncClient, dict[str, str], Path],
) -> None:
    http, headers, repo = client
    enrolled = await http.post("/repositories", headers=headers, json={"path": str(repo)})
    repo_id = enrolled.json()["repository"]["id"]

    wrote = await http.put(
        f"/repositories/{repo_id}/files/contents",
        headers=headers,
        json={"path": "hello.py", "content": "applied\n"},
    )
    assert wrote.status_code == 200

    committed = await http.post(
        f"/repositories/{repo_id}/commits",
        headers=headers,
        json={"message": "Apply hello.py", "paths": ["hello.py"]},
    )
    assert committed.status_code == 200

    (repo / "hello.py").write_text("later\n", encoding="utf-8")
    listed = await http.get(f"/repositories/{repo_id}/changes", headers=headers)
    by_path = {item["path"]: item for item in listed.json()["changes"]}
    assert by_path["hello.py"]["from_chat"] is False
