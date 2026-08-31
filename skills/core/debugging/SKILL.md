---
name: debugging
description: Reproduce a failure, isolate the cause, and keep the fix bounded.
license: AGPL-3.0-or-later
compatibility: kronos
allowed-tools: Read Write Grep
metadata:
  category: debugging
  capabilities:
    - debug
  permissions:
    - worktree_read
    - worktree_write
  scope: core
---

# Debugging

Reproduce the failure first. Isolate with a failing test. Keep the fix inside the reported scope.
