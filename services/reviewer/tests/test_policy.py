# SPDX-License-Identifier: AGPL-3.0-or-later
"""Trusted policy is loaded from the base SHA, never the PR head."""

from __future__ import annotations

import pytest
from tests.support import BASE_SHA, HEAD_SHA, FakeGit, policy_mapping

from kronos_reviewer.policy import PolicySourceError, load_trusted_policy


def test_load_trusted_policy_reads_base_not_head() -> None:
    git = FakeGit()
    git.add_policy(BASE_SHA, policy_mapping(freeze=True, risk="high"))
    git.add_policy(HEAD_SHA, policy_mapping(freeze=False, risk="low"))
    policy = load_trusted_policy(git, base_sha=BASE_SHA, head_sha=HEAD_SHA)
    assert policy.autonomy.freeze is True
    assert policy.risk.floor == "high"
    assert git.reads == [(".kronos/config.yaml", BASE_SHA)]
    assert (".kronos/config.yaml", HEAD_SHA) not in git.reads


def test_refuses_when_caller_asks_for_head_policy() -> None:
    git = FakeGit()
    git.add_policy(HEAD_SHA, policy_mapping(freeze=False))
    with pytest.raises(PolicySourceError, match="base"):
        load_trusted_policy(git, base_sha=HEAD_SHA, head_sha=HEAD_SHA)


def test_load_trusted_policy_parses_repository_template() -> None:
    from pathlib import Path

    from kronos_reviewer.policy import POLICY_PATH

    template = (
        Path(__file__).resolve().parents[3] / "templates" / "repository" / "config.yaml"
    )
    git = FakeGit()
    git.add(BASE_SHA, POLICY_PATH, template.read_text(encoding="utf-8"))
    policy = load_trusted_policy(git, base_sha=BASE_SHA, head_sha=HEAD_SHA)
    assert policy.schema_version == 2
    assert policy.commands.test == ()
    assert policy.autonomy.freeze is True
