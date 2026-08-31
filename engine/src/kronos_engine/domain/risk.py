# SPDX-License-Identifier: AGPL-3.0-or-later
"""Size, risk, and value clamps. Models cannot shrink the deterministic baseline."""

from __future__ import annotations

from kronos_engine.domain.policy import clamp_risk, clamp_size, clamp_value


def apply_planner_size(baseline: str, proposed: str) -> str:
    return clamp_size(baseline, proposed)


def apply_planner_risk(current: str, proposed: str) -> str:
    return clamp_risk(current, proposed)


def apply_planner_value(current: str, proposed: str) -> str:
    return clamp_value(current, proposed)
