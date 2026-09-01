# Security policy

Kronos is licensed under GNU AGPL v3.0. Tell us about security problems in private so we can fix them before they are public.

## Reporting a vulnerability

Use [GitHub private vulnerability reporting](https://github.com/shn3g/kronos/security/advisories/new) for this repository.

Include:

- What you were using (`apps/desktop`, `engine`, `services/reviewer`, GitHub Apps, Telegram, indexing, sandbox, policy, CI, or docs)
- Kronos version or git revision
- Steps to reproduce and what an attacker could do
- Whether credentials, repositories, or user data are involved

Do not open a public issue for unpatched vulnerabilities, leaked secrets, or exploit details.

If the advisory form is unavailable, email the repository owner through the GitHub profile listed on [github.com/shn3g](https://github.com/shn3g). Put `Kronos security` in the subject line.

## What is in scope

- The desktop app, local engine, reviewer process, and packaging scripts in this repository
- How credentials are stored and used
- Escaping the sandbox, or getting around written policy
- GitHub Apps Kronos uses to automate repositories and isolated review
- Telegram allowlists, bot tokens, and unauthorized chats
- Local indexing of enrolled repositories
- Supply-chain issues in committed lockfiles and GitHub Actions workflows

Still welcome when you can show a concrete bypass:

- Model quality problems that become a security issue
- Prompt injection from untrusted repository text

Out of scope:

- Bugs in GitHub or Telegram themselves. Report those to the vendor.

## Response

Maintainers aim to acknowledge reports within 5 business days and to share a plan once the issue is reproduced. Fixes land under AGPL-3.0 like all other contributions.

## Coordinated disclosure

Please wait for a patched release or an agreed public date before sharing exploit details. Credit is offered in the advisory unless you ask to remain anonymous.
