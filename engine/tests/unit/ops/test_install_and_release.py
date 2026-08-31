# SPDX-License-Identifier: AGPL-3.0-or-later
"""Install, upgrade, incompatible refusal, rollback, checksums, SBOM, provenance."""

from __future__ import annotations

from pathlib import Path

import pytest

from kronos_engine.ops.lifecycle import (
    IncompatibleVersion,
    install,
    rollback,
    upgrade,
)
from kronos_engine.ops.release import (
    UnsignedReleaseError,
    assert_signed,
    write_checksums,
    write_provenance,
    write_sbom,
)


def test_install_upgrade_and_rollback_keep_previous_version(tmp_path: Path) -> None:
    target = tmp_path / "machine"
    state = install(target, version="0.1.0", engine_version="0.1.0")
    assert state.version == "0.1.0"
    assert (target / "current" / "version.json").is_file()
    upgraded = upgrade(
        target,
        to_version="0.2.0",
        engine_version="0.2.0",
        min_client_version="0.1.0",
        client_version="0.2.0",
    )
    assert upgraded.version == "0.2.0"
    assert upgraded.previous_version == "0.1.0"
    rolled = rollback(target)
    assert rolled.version == "0.1.0"


def test_incompatible_client_engine_is_refused(tmp_path: Path) -> None:
    target = tmp_path / "machine"
    install(target, version="0.1.0", engine_version="0.1.0")
    with pytest.raises(IncompatibleVersion):
        upgrade(
            target,
            to_version="2.0.0",
            engine_version="2.0.0",
            min_client_version="2.0.0",
            client_version="0.1.0",
        )
    assert (target / "current" / "version.json").read_text(encoding="utf-8").find("0.1.0") >= 0


def test_checksums_sbom_and_provenance_ship_unsigned_without_keys(tmp_path: Path) -> None:
    artifacts = tmp_path / "dist"
    artifacts.mkdir()
    (artifacts / "Kronos_0.1.0_x64-setup.exe").write_bytes(b"nsis-bytes")
    (artifacts / "kronos_0.1.0_amd64.deb").write_bytes(b"deb-bytes")
    (artifacts / "Kronos.app").write_bytes(b"app-bytes")
    sums = write_checksums(artifacts)
    text = sums.read_text(encoding="utf-8")
    assert "Kronos_0.1.0_x64-setup.exe" in text
    assert "kronos_0.1.0_amd64.deb" in text
    sbom = write_sbom(
        tmp_path / "sbom.cdx.json",
        packages=(
            {"name": "kronos-engine", "version": "0.1.0", "license": "AGPL-3.0-or-later"},
            {"name": "@kronos/desktop", "version": "0.1.0", "license": "AGPL-3.0-or-later"},
        ),
    )
    sbom_text = sbom.read_text(encoding="utf-8")
    assert "kronos-engine" in sbom_text
    assert "AGPL-3.0-or-later" in sbom_text
    provenance = write_provenance(
        tmp_path / "provenance.json",
        git_sha="3b6bb6851fcf66894442fce9db6d357f8c31a412",
        builder="local-test",
    )
    assert "3b6bb6851fcf66894442fce9db6d357f8c31a412" in provenance.read_text(encoding="utf-8")
    with pytest.raises(UnsignedReleaseError):
        assert_signed(None, claim=True)
    assert_signed(None, claim=False) is None
