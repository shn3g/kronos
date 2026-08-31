---
name: refactoring
description: Change structure only while tests stay red-green and behavior holds.
license: AGPL-3.0-or-later
compatibility: kronos
allowed-tools: Read Write Grep
metadata:
  category: refactor
  capabilities:
    - refactor
  permissions:
    - worktree_read
    - worktree_write
  scope: core
---

# Refactoring

Refactor after a failing test is green. Keep behavior. Do not mix feature work into a structural pass.
