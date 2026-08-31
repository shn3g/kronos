# SPDX-License-Identifier: AGPL-3.0-or-later
"""Deploy unit files and release workflow exist and fail closed without signing keys."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def test_platform_unit_files_and_release_workflow_exist() -> None:
    windows = ROOT / "deploy" / "windows"
    systemd = ROOT / "deploy" / "systemd" / "kronos-engine.service"
    launchd = ROOT / "deploy" / "launchd" / "com.kronos.engine.plist"
    release = ROOT / ".github" / "workflows" / "release.yml"
    assert (windows / "install.ps1").is_file()
    assert (windows / "upgrade.ps1").is_file()
    assert (windows / "rollback.ps1").is_file()
    assert systemd.is_file()
    assert "Restart=on-failure" in systemd.read_text(encoding="utf-8")
    assert launchd.is_file()
    text = release.read_text(encoding="utf-8")
    assert "sha256" in text.lower() or "checksum" in text.lower()
    assert "sbom" in text.lower()
    assert "provenance" in text.lower()
    assert "TAURI_SIGNING_PRIVATE_KEY" in text
    assert "fail" in text.lower()
    assert "if-no-files-found: error" in text
    assert "--claim-signed" in text
    unit = systemd.read_text(encoding="utf-8")
    assert "StateDirectory=" in unit or "ReadWritePaths=" in unit
    assert "ProtectHome=read-only" not in unit
    installer = (windows / "install.ps1").read_text(encoding="utf-8")
    assert "Copy-Item" in installer
    assert "Payload" in installer
