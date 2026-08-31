# SPDX-License-Identifier: AGPL-3.0-or-later
"""Parse Telegram commands and call GoalService. No parallel state machine."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from kronos_engine.application.goals import GoalService
from kronos_engine.application.notifications import NotificationService
from kronos_engine.application.repositories import RepositoryService
from kronos_engine.domain.entities import GoalId, IdentifierError, RepositoryId
from kronos_engine.domain.goals import (
    GoalRecord,
    GoalSource,
    GoalSpec,
    GoalState,
    GoalValidationError,
    InvalidTransition,
)
from kronos_engine.ports.secrets import SecretStore
from kronos_engine.state.telegram import SqliteTelegramStore
from kronos_engine.telegram.auth import (
    BOT_TOKEN_REF,
    AmbiguousRepository,
    TelegramAuthorizer,
    TelegramRateLimited,
    UnauthorizedTelegram,
)
from kronos_engine.telegram.client import TelegramBotClient, TelegramUpdate
from kronos_engine.telegram.formatting import (
    format_help,
    format_state_change,
    format_status_line,
    redact_secrets,
)

_GOAL_LINE = re.compile(
    r"^/goal(?:\s+repo:(?P<repo>\S+))?\s*(?:\|\s*)?(?P<body>.*)$",
    re.IGNORECASE | re.DOTALL,
)


@dataclass(frozen=True, slots=True)
class ParsedCommand:
    name: str
    goal_id: str | None = None
    repository_id: str | None = None
    title: str | None = None
    success_criteria: str | None = None
    non_goals: str | None = None
    risk_ceiling: str | None = None


class TelegramConnector:
    def __init__(
        self,
        *,
        client: TelegramBotClient,
        store: SqliteTelegramStore,
        secrets: SecretStore,
        goals: GoalService,
        repos: RepositoryService,
        notifications: NotificationService,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._client = client
        self._store = store
        self._secrets = secrets
        self._goals = goals
        self._repos = repos
        self.notifications = notifications
        self._auth = TelegramAuthorizer(store, clock=clock)

    def poll(self) -> int:
        if not self._secrets.get(BOT_TOKEN_REF):
            return 0
        offset = self._store.load().last_update_offset
        updates = self._client.get_updates(offset)
        handled = 0
        for update in updates:
            self.handle_update(update)
            handled += 1
        return handled

    def handle_update(self, update: TelegramUpdate) -> None:
        if self._store.seen(update.update_id):
            self._store.commit_update(update.update_id)
            return
        try:
            self._auth.require_allowed(update.user_id, update.chat_id)
        except UnauthorizedTelegram:
            self._store.commit_update(update.update_id)
            return
        parsed = parse_command(update.text)
        approval = parsed is not None and parsed.name == "approval"
        try:
            self._auth.consume(update.user_id, approval=approval)
        except TelegramRateLimited:
            self._reply(update.chat_id, "rate limit")
            self._store.commit_update(update.update_id)
            return
        try:
            reply = self._dispatch(parsed, update.text)
        except AmbiguousRepository as error:
            reply = str(error)
        except (
            GoalValidationError,
            InvalidTransition,
            LookupError,
            IdentifierError,
            ValueError,
        ) as error:
            reply = str(error)
        if reply:
            self._reply(update.chat_id, reply)
        self._store.commit_update(update.update_id)

    def _dispatch(self, parsed: ParsedCommand | None, raw: str) -> str:
        if parsed is None:
            return format_help()
        if parsed.name == "help":
            return format_help()
        if parsed.name == "goal":
            return self._create_goal(parsed)
        if parsed.name == "status":
            return self._status(parsed.goal_id)
        if parsed.name == "pause":
            return self._transition(parsed.goal_id, GoalState.PAUSED, "telegram pause")
        if parsed.name == "resume":
            return self._transition(parsed.goal_id, GoalState.ACTIVE, "telegram resume")
        if parsed.name == "approval":
            return self._transition(parsed.goal_id, GoalState.ACTIVE, "telegram-approval")
        _ = raw
        return format_help()

    def _create_goal(self, parsed: ParsedCommand) -> str:
        enrolled = [item.id.value for item in self._repos.list()]
        repo_id = self._auth.resolve_repository(parsed.repository_id, enrolled)
        spec = GoalSpec(
            repository_id=RepositoryId(repo_id),
            title=redact_secrets(parsed.title or ""),
            success_criteria=redact_secrets(parsed.success_criteria or ""),
            non_goals=redact_secrets(parsed.non_goals or ""),
            risk_ceiling=parsed.risk_ceiling or "low",
            source=GoalSource.TELEGRAM,
            max_attempts=3,
        )
        created = self._goals.create(spec)
        return redact_secrets(f"created {created.id.value} {created.title} {created.state.value}")

    def _status(self, goal_id: str | None) -> str:
        if goal_id:
            listed: tuple[GoalRecord, ...] = (self._goals.get(GoalId(goal_id)),)
        else:
            listed = tuple(self._goals.list())
        if not listed:
            return "no goals"
        lines: list[str] = []
        for goal in listed:
            pr_url = None
            for task in self._goals.list_tasks(goal.id):
                if task.pr_url:
                    pr_url = task.pr_url
                    break
            lines.append(
                format_status_line(
                    title=goal.title,
                    state=goal.state.value,
                    goal_id=goal.id.value,
                    reason=goal.stop_reason,
                    pr_url=pr_url,
                )
            )
        return "\n".join(lines)

    def _transition(self, goal_id: str | None, target: GoalState, reason: str) -> str:
        if not goal_id:
            return "goal id is required"
        goal = self._goals.transition(GoalId(goal_id), target, reason=reason)
        return format_state_change(title=goal.title, state=goal.state.value, extra=reason)

    def _reply(self, chat_id: int, text: str) -> None:
        self._client.send_message(chat_id, text)


def parse_command(text: str) -> ParsedCommand | None:
    stripped = text.strip()
    if not stripped.startswith("/"):
        return None
    head, _, rest = stripped.partition(" ")
    name = head[1:].split("@", 1)[0].lower()
    if name in {"help", "start"}:
        return ParsedCommand(name="help")
    if name == "status":
        return ParsedCommand(name="status", goal_id=rest.strip() or None)
    if name in {"pause", "resume", "approval"}:
        return ParsedCommand(name=name, goal_id=rest.strip() or None)
    if name == "goal":
        goal_line = f"/{name}"
        if rest:
            goal_line = f"{goal_line} {rest}"
        return _parse_goal(goal_line)
    return None


def _parse_goal(text: str) -> ParsedCommand:
    match = _GOAL_LINE.match(text.strip())
    repo_id = match.group("repo") if match else None
    body = match.group("body") if match else ""
    parts = [part.strip() for part in body.split("|")]
    title = parts[0] if len(parts) > 0 else None
    criteria = parts[1] if len(parts) > 1 else None
    non_goals = parts[2] if len(parts) > 2 else None
    risk = parts[3] if len(parts) > 3 else None
    return ParsedCommand(
        name="goal",
        repository_id=repo_id,
        title=title or None,
        success_criteria=criteria or None,
        non_goals=non_goals or None,
        risk_ceiling=risk or None,
    )
