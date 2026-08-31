# SPDX-License-Identifier: AGPL-3.0-or-later
"""Propose and apply repository rulesets without silently weakening protections."""

from __future__ import annotations

from kronos_engine.adapters.github.client import GitHubClient
from kronos_engine.domain.github import KRONOS_REVIEW_CHECK_NAME
from kronos_engine.ports.forge import (
    ForgeTarget,
    OperatorConfirmationRequired,
    RequiredCheck,
    RulesetProposal,
    RulesetRef,
    RulesetWouldWeaken,
    default_required_checks,
)

RULESET_NAME = "kronos-integration"


def propose_ruleset(
    client: GitHubClient,
    target: ForgeTarget,
    reviewer_integration_id: int,
) -> RulesetProposal:
    existing = _load_existing(client, target)
    checks = _union_checks(existing, default_required_checks(reviewer_integration_id))
    return RulesetProposal(
        name=RULESET_NAME,
        required_checks=checks,
        strict=True,
        bypass_actors=(),
    )


def apply_ruleset(
    client: GitHubClient,
    target: ForgeTarget,
    proposal: RulesetProposal,
    *,
    confirm: bool,
) -> RulesetRef:
    if not confirm:
        raise OperatorConfirmationRequired(
            "operator confirmation is required before applying a ruleset"
        )
    existing = _load_existing(client, target)
    _assert_not_weaker(existing, proposal)
    payload = _payload(target, proposal, existing)
    if existing is not None and _equivalent(existing, proposal):
        return RulesetRef(id=_as_int(existing.get("id")), strict=True, created=False)
    if existing is None:
        created = client.request_json(
            "POST",
            f"/repos/{target.owner}/{target.repo}/rulesets",
            json_body=payload,
        )
        assert isinstance(created, dict)
        return RulesetRef(id=_as_int(created.get("id")), strict=True, created=True)
    updated = client.request_json(
        "PUT",
        f"/repos/{target.owner}/{target.repo}/rulesets/{existing['id']}",
        json_body=payload,
    )
    assert isinstance(updated, dict)
    return RulesetRef(id=_as_int(updated.get("id")), strict=True, created=False)


def _load_existing(client: GitHubClient, target: ForgeTarget) -> dict[str, object] | None:
    listed = client.request_json("GET", f"/repos/{target.owner}/{target.repo}/rulesets")
    if not isinstance(listed, list):
        return None
    named: dict[str, object] | None = None
    for item in listed:
        if isinstance(item, dict) and item.get("name") == RULESET_NAME:
            named = item
            break
    if named is None:
        return None
    detail = client.request_json(
        "GET",
        f"/repos/{target.owner}/{target.repo}/rulesets/{named['id']}",
    )
    return detail if isinstance(detail, dict) else named


def _union_checks(
    existing: dict[str, object] | None, required: tuple[RequiredCheck, ...]
) -> tuple[RequiredCheck, ...]:
    merged: dict[str, RequiredCheck] = {}
    for item in _iter_checks(existing):
        merged[item.context] = item
    for item in required:
        merged[item.context] = item
    return tuple(merged.values())


def _iter_checks(existing: dict[str, object] | None) -> tuple[RequiredCheck, ...]:
    if not existing:
        return ()
    found: list[RequiredCheck] = []
    rules = existing.get("rules")
    if not isinstance(rules, list):
        return ()
    for rule in rules:
        if not isinstance(rule, dict) or rule.get("type") != "required_status_checks":
            continue
        parameters = rule.get("parameters")
        if not isinstance(parameters, dict):
            continue
        checks = parameters.get("required_status_checks")
        if not isinstance(checks, list):
            continue
        for check in checks:
            if not isinstance(check, dict):
                continue
            context = check.get("context")
            if not isinstance(context, str):
                continue
            integration = check.get("integration_id")
            found.append(
                RequiredCheck(
                    context=context,
                    integration_id=integration if isinstance(integration, int) else None,
                )
            )
    return tuple(found)


def _assert_not_weaker(existing: dict[str, object] | None, proposal: RulesetProposal) -> None:
    if proposal.strict is not True:
        raise RulesetWouldWeaken("strict required status checks must stay true")
    if proposal.bypass_actors:
        raise RulesetWouldWeaken("bypass actors would weaken the ruleset")
    kronos = next(
        (item for item in proposal.required_checks if item.context == KRONOS_REVIEW_CHECK_NAME),
        None,
    )
    if kronos is None or kronos.integration_id is None:
        raise RulesetWouldWeaken(
            "integration_id is required on kronos-review (kronos-reviewer)"
        )
    contexts = {item.context for item in proposal.required_checks}
    if KRONOS_REVIEW_CHECK_NAME not in contexts:
        raise RulesetWouldWeaken("check name kronos-review (kronos-reviewer) is required")
    existing_contexts = {item.context for item in _iter_checks(existing)}
    dropped = existing_contexts - contexts
    if dropped:
        raise RulesetWouldWeaken("check would drop an existing required status check")


def _equivalent(existing: dict[str, object], proposal: RulesetProposal) -> bool:
    current = {item.context: item.integration_id for item in _iter_checks(existing)}
    proposed = {item.context: item.integration_id for item in proposal.required_checks}
    if current != proposed:
        return False
    rules = existing.get("rules")
    if isinstance(rules, list):
        for rule in rules:
            if not isinstance(rule, dict) or rule.get("type") != "required_status_checks":
                continue
            parameters = rule.get("parameters")
            if isinstance(parameters, dict):
                if parameters.get("strict_required_status_checks_policy") is not True:
                    return False
    bypass = existing.get("bypass_actors")
    if isinstance(bypass, list) and bypass:
        return False
    return True


def _kept_rules(existing: dict[str, object] | None) -> list[object]:
    if existing is None:
        return []
    rules = existing.get("rules")
    if not isinstance(rules, list):
        return []
    kept: list[object] = []
    for rule in rules:
        if isinstance(rule, dict) and rule.get("type") != "required_status_checks":
            kept.append(rule)
    return kept


def _check_payload(item: RequiredCheck) -> dict[str, object]:
    payload: dict[str, object] = {"context": item.context}
    if item.integration_id is not None:
        payload["integration_id"] = item.integration_id
    return payload


def _payload(
    target: ForgeTarget,
    proposal: RulesetProposal,
    existing: dict[str, object] | None,
) -> dict[str, object]:
    exclude: list[str] = []
    if target.protected_branch != target.integration_branch:
        exclude = [f"refs/heads/{target.protected_branch}"]
    status_rule = {
        "type": "required_status_checks",
        "parameters": {
            "strict_required_status_checks_policy": True,
            "required_status_checks": [_check_payload(item) for item in proposal.required_checks],
        },
    }
    return {
        "name": proposal.name,
        "target": "branch",
        "enforcement": "active",
        "bypass_actors": [],
        "conditions": {
            "ref_name": {
                "include": [f"refs/heads/{target.integration_branch}"],
                "exclude": exclude,
            }
        },
        "rules": [*_kept_rules(existing), status_rule],
    }


def _as_int(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise TypeError("expected int")
