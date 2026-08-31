---
name: migrations
description: Write expand-contract schema migrations with rollback notes.
license: AGPL-3.0-or-later
compatibility: kronos
allowed-tools: Read Write Grep
metadata:
  category: data
  capabilities:
    - migrations
  permissions:
    - worktree_read
    - worktree_write
  scope: core
---

# Migrations

Use expand-contract migrations. Add rollback notes. Never drop a column in the same change that still reads it.
