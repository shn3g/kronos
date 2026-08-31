# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reviewer check name binding. The controller App must not post this check."""

from __future__ import annotations

from kronos_engine.domain.github import KRONOS_REVIEW_CHECK_NAME


class ControllerCannotPostReviewCheck(RuntimeError):
    """The controller App is not allowed to publish the reviewer check."""


def assert_controller_cannot_post(name: str) -> None:
    _ = name
    if name == KRONOS_REVIEW_CHECK_NAME:
        raise ControllerCannotPostReviewCheck(
            "the controller App cannot publish the Kronos reviewer check"
        )
    raise ControllerCannotPostReviewCheck("the controller App cannot publish GitHub check runs")
