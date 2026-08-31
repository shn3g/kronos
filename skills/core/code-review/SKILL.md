---
name: code-review
description: Review a diff for correctness, tests, and scope rather than the author.
license: AGPL-3.0-or-later
compatibility: kronos
allowed-tools: Read Write Grep
metadata:
  category: review
  capabilities:
    - review
  permissions:
    - worktree_read
  scope: core
---

# Code Review

Review the diff and tests. Reject missing evidence. Do not rubber-stamp the author identity.
