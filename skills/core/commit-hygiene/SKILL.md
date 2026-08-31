---
name: commit-hygiene
description: Write conventional commits without secrets or generated junk.
license: AGPL-3.0-or-later
compatibility: kronos
allowed-tools: Read Write Grep
metadata:
  category: git
  capabilities:
    - commit
  permissions:
    - worktree_read
    - worktree_write
  scope: core
---

# Commit Hygiene

Use conventional commits. Do not commit secrets, credentials, or generated junk. Keep the subject under 72 characters.
