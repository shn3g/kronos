---
name: dependency-changes
description: Change lockfiles and pins with license and compatibility checks.
license: AGPL-3.0-or-later
compatibility: kronos
allowed-tools: Read Write Grep
metadata:
  category: deps
  capabilities:
    - dependencies
  permissions:
    - worktree_read
    - worktree_write
  scope: core
---

# Dependency Changes

Pin dependencies. Check licenses. Do not widen the lockfile without a failing test for the needed API.
