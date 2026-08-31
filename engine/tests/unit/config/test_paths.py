# SPDX-License-Identifier: AGPL-3.0-or-later

from pathlib import Path

from kronos_engine.config.paths import resolve_paths


def test_env_overrides_win_over_platform_defaults(tmp_path: Path) -> None:
    data = tmp_path / "data"
    config = tmp_path / "config"
    cache = tmp_path / "cache"
    logs = tmp_path / "logs"
    paths = resolve_paths(
        environ={
            "KRONOS_DATA_HOME": str(data),
            "KRONOS_CONFIG_HOME": str(config),
            "KRONOS_CACHE_HOME": str(cache),
            "KRONOS_LOG_HOME": str(logs),
            "LOCALAPPDATA": str(tmp_path / "should-not-use"),
        },
        system="windows",
        cwd=tmp_path / "checkout",
    )
    assert paths.data == data
    assert paths.config == config
    assert paths.cache == cache
    assert paths.logs == logs


def test_windows_defaults_are_outside_the_git_work_tree(tmp_path: Path) -> None:
    checkout = tmp_path / "repo"
    checkout.mkdir()
    (checkout / ".git").mkdir()
    local = tmp_path / "Local"
    roaming = tmp_path / "Roaming"
    paths = resolve_paths(
        environ={
            "LOCALAPPDATA": str(local),
            "APPDATA": str(roaming),
        },
        system="windows",
        cwd=checkout,
    )
    assert paths.data == local / "kronos"
    assert paths.config == roaming / "kronos"
    assert paths.cache == local / "kronos" / "cache"
    assert paths.logs == local / "kronos" / "logs"
    assert checkout not in paths.data.parents
    assert checkout != paths.data
    assert paths.worktrees == paths.cache / "worktrees"
    assert "hermes" not in str(paths.data).lower()
    assert "hermes" not in str(paths.cache).lower()


def test_linux_defaults_use_xdg_dirs(tmp_path: Path) -> None:
    paths = resolve_paths(
        environ={
            "XDG_DATA_HOME": str(tmp_path / "share"),
            "XDG_CONFIG_HOME": str(tmp_path / "config"),
            "XDG_CACHE_HOME": str(tmp_path / "cache"),
            "XDG_STATE_HOME": str(tmp_path / "state"),
        },
        system="linux",
        cwd=tmp_path / "repo",
        home=tmp_path / "home",
    )
    assert paths.data == tmp_path / "share" / "kronos"
    assert paths.config == tmp_path / "config" / "kronos"
    assert paths.cache == tmp_path / "cache" / "kronos"
    assert paths.logs == tmp_path / "state" / "kronos" / "logs"


def test_macos_defaults_use_library_dirs(tmp_path: Path) -> None:
    home = tmp_path / "Users" / "dev"
    paths = resolve_paths(environ={}, system="darwin", cwd=tmp_path / "repo", home=home)
    assert paths.data == home / "Library" / "Application Support" / "kronos"
    assert paths.config == home / "Library" / "Application Support" / "kronos"
    assert paths.cache == home / "Library" / "Caches" / "kronos"
    assert paths.logs == home / "Library" / "Logs" / "kronos"
    assert paths.worktrees == paths.cache / "worktrees"
