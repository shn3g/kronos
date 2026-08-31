# Telegram

Telegram is a first-party connector, not a separate agent runtime. It calls the same engine application services as Desktop.

## What it can do

- Create a goal for a selected repository
- View goals, tasks, failures, budgets, and pull request links
- Pause or resume allowed work
- Approve explicitly human-gated operations
- Receive test, review, merge, breaker, and security alerts
- Receive generated artifacts and reports

## What it must not do

Messages never include raw GitHub tokens, reviewer PEMs, or the install bearer. Allowlist changes go through authenticated engine APIs. Unauthorized chats are rejected.

Bot tokens live in the OS secret store. `POST /telegram/token` exists for native import and must not echo the secret.

## Authorization

Only allowlisted Telegram user ids can create goals or change autonomy. Authorization tests live under `engine/tests/security/test_telegram_authorization.py`.
