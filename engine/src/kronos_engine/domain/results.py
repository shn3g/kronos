# SPDX-License-Identifier: AGPL-3.0-or-later
"""Domain result and error types. No I/O."""


class AlreadyDispatchedError(Exception):
    """An outbox row was already marked dispatched."""


class LockHeldError(Exception):
    """A live foreign lease refused takeover."""


class StaleFenceError(Exception):
    """The provided fence token does not match the live lease."""
