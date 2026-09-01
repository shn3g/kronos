# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import pytest

from kronos_engine.domain.policy import (
    POLICY_SCHEMA_VERSION,
    PolicyError,
    apply_model_proposal,
    default_policy,
    parse_policy,
)


def test_indexing_policy_requires_excludes_and_size_on_schema_two() -> None:
    policy = default_policy(integration_branch="main", protected_branch="main")
    assert POLICY_SCHEMA_VERSION == 2
    assert policy.schema_version == 2
    assert policy.indexing.enabled is True
    assert policy.indexing.max_file_bytes >= 1
    assert "node_modules/" in policy.indexing.exclude_prefixes


def test_models_cannot_flip_indexing_operator_fuses() -> None:
    current = default_policy(integration_branch="main", protected_branch="main")
    proposal = _policy_dict(current)
    proposal["indexing"] = {
        "enabled": False,
        "exclude_prefixes": list(current.indexing.exclude_prefixes),
        "max_file_bytes": current.indexing.max_file_bytes,
    }
    with pytest.raises(PolicyError, match="indexing"):
        apply_model_proposal(current, proposal)


def test_unknown_indexing_fields_are_rejected() -> None:
    payload = _policy_dict(default_policy(integration_branch="main", protected_branch="main"))
    payload["indexing"]["unexpected"] = True  # type: ignore[index]
    with pytest.raises(PolicyError, match="unknown"):
        parse_policy(payload)


def test_indexing_watch_fields_default_when_missing() -> None:
    payload = _policy_dict(default_policy(integration_branch="main", protected_branch="main"))
    indexing = dict(payload["indexing"])  # type: ignore[arg-type]
    indexing.pop("watch", None)
    indexing.pop("debounce_ms", None)
    indexing.pop("extra_exclude_globs", None)
    payload["indexing"] = indexing
    policy = parse_policy(payload)
    assert policy.schema_version == POLICY_SCHEMA_VERSION
    assert policy.indexing.watch is True
    assert policy.indexing.debounce_ms == 500
    assert policy.indexing.extra_exclude_globs == ()


def test_indexing_watch_fields_round_trip() -> None:
    payload = _policy_dict(default_policy(integration_branch="main", protected_branch="main"))
    payload["indexing"] = {
        **dict(payload["indexing"]),  # type: ignore[dict-item]
        "watch": False,
        "debounce_ms": 250,
        "extra_exclude_globs": ["*.tmp", "scratch/"],
    }
    policy = parse_policy(payload)
    assert policy.indexing.watch is False
    assert policy.indexing.debounce_ms == 250
    assert policy.indexing.extra_exclude_globs == ("*.tmp", "scratch/")
    serialized = _policy_dict(policy)["indexing"]
    assert serialized == {
        "enabled": True,
        "exclude_prefixes": list(policy.indexing.exclude_prefixes),
        "max_file_bytes": policy.indexing.max_file_bytes,
        "watch": False,
        "debounce_ms": 250,
        "extra_exclude_globs": ["*.tmp", "scratch/"],
    }


def _policy_dict(policy: object) -> dict[str, object]:
    from kronos_engine.domain.policy import policy_to_dict

    return policy_to_dict(policy)  # type: ignore[arg-type]
