---
name: security-review
description: Check diffs for secrets, injection, authz, and sandbox escapes.
license: AGPL-3.0-or-later
compatibility: kronos
allowed-tools: Read Write Grep
metadata:
  category: security
  capabilities:
    - security
  permissions:
    - worktree_read
  scope: core
---

# Security Review

Look for leaked credentials, injection, and authz gaps. Workers must not receive reviewer credentials.
