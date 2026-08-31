---
name: backend-testing
description: Cover API and domain rules with fixtures and fail-closed assertions.
license: AGPL-3.0-or-later
compatibility: kronos
allowed-tools: Read Write Grep
metadata:
  category: testing
  capabilities:
    - backend
    - test
  permissions:
    - worktree_read
    - worktree_write
  scope: core
---

# Backend Testing

Use fixtures. Assert fail-closed status codes. Keep domain tests free of I/O.
