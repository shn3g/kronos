# SPDX-License-Identifier: AGPL-3.0-or-later
"""Version lockstep script: matching files pass, mismatches and tag drift fail."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "scripts" / "check-version-sync.py"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_version_sync", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_lockstep(root: Path, version: str) -> None:
    payload = json.dumps({"version": version}, indent=2) + "\n"
    _write(root / "package.json", payload)
    _write(
        root / "pyproject.toml",
        f'[project]\nname = "kronos-workspace"\nversion = "{version}"\n',
    )
    _write(root / "apps" / "desktop" / "package.json", payload)
    _write(
        root / "apps" / "desktop" / "src-tauri" / "tauri.conf.json",
        json.dumps({"version": version}, indent=2) + "\n",
    )
    _write(
        root / "apps" / "desktop" / "src-tauri" / "Cargo.toml",
        f'[package]\nname = "kronos"\nversion = "{version}"\n',
    )
    _write(
        root / "apps" / "desktop" / "src-tauri" / "Cargo.lock",
        f'[[package]]\nname = "kronos"\nversion = "{version}"\n',
    )
    _write(
        root / "apps" / "desktop" / "src-tauri" / "src" / "engine.rs",
        f'const CLIENT_VERSION: &str = "{version}";\n',
    )
    _write(
        root / "apps" / "desktop" / "src" / "api" / "kronosClient.ts",
        f'export const DESKTOP_CLIENT_VERSION = "{version}";\n',
    )
    _write(
        root / "engine" / "pyproject.toml",
        f'[project]\nname = "kronos-engine"\nversion = "{version}"\n',
    )
    _write(
        root / "engine" / "src" / "kronos_engine" / "__init__.py",
        f'__version__ = "{version}"\n',
    )
    _write(
        root / "services" / "reviewer" / "pyproject.toml",
        f'[project]\nname = "kronos-reviewer"\nversion = "{version}"\n',
    )
    _write(
        root / "services" / "reviewer" / "src" / "kronos_reviewer" / "__init__.py",
        f'__version__ = "{version}"\n',
    )
    _write(
        root / "engine" / "src" / "kronos_engine" / "ops" / "release_cli.py",
        (
            "write_sbom(\n"
            "    artifacts / 'sbom.cdx.json',\n"
            "    packages=(\n"
            f'        {{"name": "kronos-engine", "version": "{version}", '
            '"license": "AGPL-3.0-or-later"},\n'
            f'        {{"name": "@kronos/desktop", "version": "{version}", '
            '"license": "AGPL-3.0-or-later"},\n'
            "    ),\n"
            ")\n"
        ),
    )


def test_matching_lockstep_tree_exits_zero(tmp_path: Path) -> None:
    _write_lockstep(tmp_path, "0.2.0")
    module = _load_script()
    assert module.main(["--root", str(tmp_path)]) == 0


def test_cargo_lock_kronos_version_must_match_lockstep(tmp_path: Path) -> None:
    _write_lockstep(tmp_path, "0.2.0")
    (
        tmp_path / "apps" / "desktop" / "src-tauri" / "Cargo.lock"
    ).write_text('[[package]]\nname = "kronos"\nversion = "9.9.9"\n', encoding="utf-8")
    module = _load_script()
    assert module.main(["--root", str(tmp_path)]) == 1


def test_mismatched_lockstep_tree_exits_nonzero(tmp_path: Path) -> None:
    _write_lockstep(tmp_path, "0.2.0")
    (tmp_path / "package.json").write_text(
        json.dumps({"version": "0.1.0"}) + "\n", encoding="utf-8"
    )
    module = _load_script()
    assert module.main(["--root", str(tmp_path)]) == 1


def test_tag_ref_must_match_lockstep_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_lockstep(tmp_path, "0.2.0")
    module = _load_script()
    monkeypatch.setenv("GITHUB_REF", "refs/tags/v0.2.0")
    assert module.main(["--root", str(tmp_path)]) == 0
    monkeypatch.setenv("GITHUB_REF", "refs/tags/v9.9.9")
    assert module.main(["--root", str(tmp_path)]) == 1
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    assert module.main(["--root", str(tmp_path)]) == 0


def test_repository_lockstep_files_agree() -> None:
    module = _load_script()
    assert module.main(["--root", str(ROOT)]) == 0


def test_min_client_version_default_stays_0_1_0() -> None:
    text = (ROOT / "engine" / "src" / "kronos_engine" / "config" / "settings.py").read_text(
        encoding="utf-8"
    )
    assert 'env.get("KRONOS_MIN_CLIENT_VERSION") or "0.1.0"' in text


def test_extract_changelog_section_and_fallback() -> None:
    module = _load_script()
    changelog = (
        "# Changelog\n\n## [Unreleased]\n\n## [0.2.0] - 2026-09-01\n\n"
        "Developed as 0.1.1-0.1.6 on this branch; tagged together as 0.2.0.\n\n"
        "### Added\n\n- Chat orchestrator.\n\n## [0.1.0] - 2026-08-31\n\nPreview.\n"
    )
    section = module.extract_changelog_section(changelog, "0.2.0")
    assert section is not None
    assert "## [0.2.0] - 2026-09-01" in section
    assert "Chat orchestrator." in section
    assert "Preview." not in section
    assert module.extract_changelog_section(changelog, "9.9.9") is None


def test_write_release_notes_still_rejects_mismatched_tag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_lockstep(tmp_path, "0.2.0")
    notes = tmp_path / "notes.md"
    module = _load_script()
    assert (
        module.main(
            ["--root", str(tmp_path), "--write-release-notes", str(notes), "--tag", "v9.9.9"]
        )
        == 1
    )
    monkeypatch.delenv("GITHUB_REF", raising=False)
    monkeypatch.setenv("GITHUB_REF", "refs/tags/v9.9.9")
    assert module.main(["--root", str(tmp_path), "--write-release-notes", str(notes)]) == 1


def test_write_release_notes_uses_changelog_then_download_warnings(
    tmp_path: Path,
) -> None:
    _write_lockstep(tmp_path, "0.2.0")
    _write(
        tmp_path / "CHANGELOG.md",
        "# Changelog\n\n## [Unreleased]\n\n## [0.2.0] - 2026-09-01\n\nChat and indexing.\n",
    )
    notes = tmp_path / "notes.md"
    module = _load_script()
    assert (
        module.main(
            ["--root", str(tmp_path), "--write-release-notes", str(notes), "--tag", "v0.2.0"]
        )
        == 0
    )
    text = notes.read_text(encoding="utf-8")
    assert "Chat and indexing." in text
    assert "First public desktop build" not in text
    assert "Kronos_0.2.0_x64-setup.exe" in text
    assert "Kronos_0.2.0_amd64.deb" in text
    assert "Kronos_0.2.0_macos.app.zip" in text
    assert "Unsigned" in text
    assert "Python 3.11+" in text


def test_script_cli_subprocess_reports_mismatch(tmp_path: Path) -> None:
    _write_lockstep(tmp_path, "0.2.0")
    (tmp_path / "engine" / "src" / "kronos_engine" / "__init__.py").write_text(
        '__version__ = "0.1.0"\n', encoding="utf-8"
    )
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(tmp_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 1
    assert "mismatch" in completed.stderr.lower() or "disagree" in completed.stderr.lower()
