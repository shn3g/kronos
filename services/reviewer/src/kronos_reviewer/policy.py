# SPDX-License-Identifier: AGPL-3.0-or-later
"""Load versioned Kronos policy from the base SHA only."""

from __future__ import annotations

from collections.abc import Mapping

from kronos_engine.domain.policy import PolicyError, RepositoryPolicy, parse_policy
from kronos_engine.domain.policy_yaml import parse_simple_yaml

from kronos_reviewer.checkout import ReviewGit

POLICY_PATH = ".kronos/config.yaml"


class PolicySourceError(RuntimeError):
    """Raised when policy would be read from the PR head or is unreadable."""


def load_trusted_policy(git: ReviewGit, *, base_sha: str, head_sha: str) -> RepositoryPolicy:
    if base_sha == head_sha:
        raise PolicySourceError("trusted policy must be loaded from base, not the PR head")
    text = git.show_file(base_sha, POLICY_PATH)
    try:
        raw = parse_simple_yaml(text)
    except PolicyError as error:
        raise PolicySourceError(str(error)) from error
    if not isinstance(raw, Mapping):
        raise PolicySourceError("trusted policy must be a mapping")
    try:
        return parse_policy(raw)
    except PolicyError as error:
        raise PolicySourceError(str(error)) from error
