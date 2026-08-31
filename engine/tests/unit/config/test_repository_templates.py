# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

from tests.support.git_fixtures import init_git_repo

from kronos_engine.config.repository import TEMPLATES_ROOT, render_enrolment_preview
from kronos_engine.domain.policy import default_policy


def test_templates_include_fuses_workflow_and_codeowners() -> None:
    config = (TEMPLATES_ROOT / "repository" / "config.yaml").read_text(encoding="utf-8")
    workflow = (TEMPLATES_ROOT / "github" / "kronos-pr.yml").read_text(encoding="utf-8")
    assert "freeze: true" in config
    assert "invent_issues: false" in config
    assert "mode: observe" in config
    assert "hermes" not in config.lower()
    assert "hermes" not in workflow.lower()
    assert "kronos-pr" in workflow
    assert ".kronos/**" in (TEMPLATES_ROOT / "github" / "CODEOWNERS").read_text(encoding="utf-8")


def test_preview_is_a_diff_and_does_not_write(tmp_path: Path) -> None:
    root = init_git_repo(
        tmp_path / "preview-app",
        origin="https://github.com/acme/preview-app.git",
        files={"README.md": "app\n"},
    )
    policy = default_policy(integration_branch="main", protected_branch="main")
    preview = render_enrolment_preview(root, policy, owner="@acme")
    paths = {item.path for item in preview.files}
    assert ".kronos/config.yaml" in paths
    assert ".github/workflows/kronos-pr.yml" in paths
    assert ".github/CODEOWNERS" in paths
    codeowners = next(item for item in preview.files if item.path == ".github/CODEOWNERS")
    assert ".kronos/**" in codeowners.content
    assert "@acme" in codeowners.content
    assert not (root / ".kronos").exists()
    assert not (root / ".github" / "workflows" / "kronos-pr.yml").exists()
    assert not (root / ".github" / "CODEOWNERS").exists()
    assert preview.wrote_files is False
    assert preview.committed is False
    assert preview.pushed is False
    added = any(
        line.startswith("+")
        for item in preview.files
        for line in item.unified_diff.splitlines()
    )
    assert added
