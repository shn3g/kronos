# SPDX-License-Identifier: AGPL-3.0-or-later
"""GitHub identity constants. Pure values. No I/O."""

from __future__ import annotations

KRONOS_REVIEW_CHECK_NAME = "kronos-review (kronos-reviewer)"
CONTROLLER_APP_ROLE = "controller"
REVIEWER_APP_ROLE = "reviewer"
APP_ROLES: tuple[str, ...] = (CONTROLLER_APP_ROLE, REVIEWER_APP_ROLE)
CONTROLLER_PRIVATE_KEY_REF = "github:controller:private_key"
REVIEWER_PRIVATE_KEY_REF = "github:reviewer:private_key"
POLL_MODE_CONDITIONAL = "conditional"
