# Security policy

Kronos is licensed under GNU AGPL v3.0. Security reports are handled privately so operators can patch before public disclosure.

## Reporting a vulnerability

Use [GitHub private vulnerability reporting](https://github.com/shn3g/kronos/security/advisories/new) for this repository.

Include:

- Affected component (`apps/desktop`, `engine`, `services/reviewer`, GitHub Apps, Telegram, indexing, sandbox, policy, CI, or docs)
- Kronos version or git revision
- Reproduction steps and expected impact
- Whether credentials, repositories, or user data are involved

Do not open a public issue for unpatched vulnerabilities, leaked secrets, or exploit details.

If the advisory form is unavailable, email the repository owner through the GitHub profile listed on [github.com/shn3g](https://github.com/shn3g). Put `Kronos security` in the subject line.

## Scope

In scope:

- Desktop client, local engine, reviewer process, and packaging scripts in this repository
- Credential handling, sandbox escapes, and policy bypasses
- GitHub Apps Kronos uses for repository automation and isolated review
- Telegram authorization (allowlists, bot-token handling, unauthorized chats)
- Local indexing of enrolled repositories
- Supply-chain issues in committed lockfiles and GitHub Actions workflows

Product quality (still welcome when a concrete bypass exists):

- Model quality
- Prompt injection against untrusted repository text

Out of scope:

- Bugs in the GitHub or Telegram platforms themselves. Report those to the vendor.

## Response

Maintainers aim to acknowledge reports within 5 business days and to share a remediation plan once the issue is reproduced. Fixes land under AGPL-3.0 like all other contributions.

## Coordinated disclosure

Please wait for a patched release or an agreed public date before sharing exploit details. Credit is offered in the advisory unless you ask to remain anonymous.
