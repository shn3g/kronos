# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for scripts/release-latest-json.py."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "scripts" / "release-latest-json.py"

_spec = importlib.util.spec_from_file_location("release_latest_json", SCRIPT)
assert _spec and _spec.loader
release_latest_json = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(release_latest_json)

MissingSignatureError = release_latest_json.MissingSignatureError
build_latest_json = release_latest_json.build_latest_json
discover_platforms = release_latest_json.discover_platforms
main = release_latest_json.main


def test_discover_platforms_builds_valid_latest_json(tmp_path: Path) -> None:
    artifacts = tmp_path / "bundle"
    nsis = artifacts / "nsis"
    nsis.mkdir(parents=True)
    exe = nsis / "Kronos_0.5.0_x64-setup.exe"
    sig = nsis / "Kronos_0.5.0_x64-setup.exe.sig"
    exe.write_bytes(b"nsis")
    sig.write_text("windows-signature", encoding="utf-8")

    appimage = artifacts / "appimage"
    appimage.mkdir()
    image = appimage / "Kronos_0.5.0_amd64.AppImage"
    image_sig = appimage / "Kronos_0.5.0_amd64.AppImage.sig"
    image.write_bytes(b"appimage")
    image_sig.write_text("linux-signature", encoding="utf-8")

    macos = artifacts / "macos"
    macos.mkdir()
    archive = macos / "Kronos.app.tar.gz"
    archive_sig = macos / "Kronos.app.tar.gz.sig"
    archive.write_bytes(b"mac")
    archive_sig.write_text("darwin-signature", encoding="utf-8")

    platforms = discover_platforms(
        artifacts,
        url_builder=lambda path: f"https://example.test/{path.name}",
    )
    payload = build_latest_json(
        version="0.5.0",
        notes="## [0.5.0]\n\nOne-click.",
        platforms=platforms,
        pub_date="2026-09-02T12:00:00Z",
    )

    assert payload["version"] == "0.5.0"
    assert payload["notes"].startswith("## [0.5.0]")
    assert payload["platforms"]["windows-x86_64"]["signature"] == "windows-signature"
    assert payload["platforms"]["linux-x86_64"]["url"].endswith(".AppImage")
    assert payload["platforms"]["darwin-aarch64"]["signature"] == "darwin-signature"


def test_darwin_arch_marker_overrides_default_flag(tmp_path: Path) -> None:
    artifacts = tmp_path / "bundle"
    macos = artifacts / "macos"
    macos.mkdir(parents=True)
    archive = macos / "Kronos.app.tar.gz"
    archive_sig = macos / "Kronos.app.tar.gz.sig"
    archive.write_bytes(b"mac")
    archive_sig.write_text("darwin-signature", encoding="utf-8")
    (artifacts / "darwin-arch.txt").write_text("x86_64\n", encoding="utf-8")

    platforms = discover_platforms(
        artifacts,
        url_builder=lambda path: f"https://example.test/{path.name}",
        darwin_arch="aarch64",
    )
    assert "darwin-x86_64" in platforms
    assert "darwin-aarch64" not in platforms


def test_allow_missing_signatures_omits_latest_json(tmp_path: Path) -> None:
    artifacts = tmp_path / "bundle"
    nsis = artifacts / "nsis"
    nsis.mkdir(parents=True)
    (nsis / "Kronos_0.5.0_x64-setup.exe").write_bytes(b"nsis")
    out = tmp_path / "latest.json"

    exit_code = main(
        [
            "--artifacts",
            str(artifacts),
            "--version",
            "0.5.0",
            "--release-base-url",
            "https://example.test",
            "--output",
            str(out),
            "--allow-missing-signatures",
        ]
    )
    assert exit_code == 0
    assert not out.is_file()


def test_missing_signature_fails_closed(tmp_path: Path) -> None:
    artifacts = tmp_path / "bundle"
    nsis = artifacts / "nsis"
    nsis.mkdir(parents=True)
    (nsis / "Kronos_0.5.0_x64-setup.exe").write_bytes(b"nsis")

    with pytest.raises(MissingSignatureError):
        discover_platforms(
            artifacts,
            url_builder=lambda path: f"https://example.test/{path.name}",
        )


def test_main_writes_json_from_fixtures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    artifacts = tmp_path / "bundle"
    nsis = artifacts / "nsis"
    nsis.mkdir(parents=True)
    exe = nsis / "Kronos_0.4.0_x64-setup.exe"
    sig = nsis / "Kronos_0.4.0_x64-setup.exe.sig"
    exe.write_bytes(b"nsis")
    sig.write_text("sig", encoding="utf-8")

    out = tmp_path / "latest.json"
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("## [0.4.0]\n\nWorkbench release.\n", encoding="utf-8")

    exit_code = main(
        [
            "--artifacts",
            str(artifacts),
            "--version",
            "0.4.0",
            "--changelog",
            str(changelog),
            "--release-base-url",
            "https://github.com/shn3g/kronos/releases/download/v0.4.0",
            "--output",
            str(out),
        ]
    )
    assert exit_code == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["version"] == "0.4.0"
    assert payload["platforms"]["windows-x86_64"]["signature"] == "sig"
    assert payload["platforms"]["windows-x86_64"]["url"].endswith("Kronos_0.4.0_x64-setup.exe")
