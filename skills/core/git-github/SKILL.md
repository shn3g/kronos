---
name: git-github
description: Use branches, draft PRs, and the integration branch without touching the protected default.
license: AGPL-3.0-or-later
compatibility: kronos
allowed-tools: Read Write Grep
metadata:
  category: git
  capabilities:
    - git
  permissions:
    - worktree_read
  scope: core
---

# Git Github

Open draft PRs onto the integration branch. Never push the protected default. Bind review to the exact head SHA.
