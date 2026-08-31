---
name: ci-gates
description: Require configured checks on the exact head SHA before merge.
license: AGPL-3.0-or-later
compatibility: kronos
allowed-tools: Read Write Grep
metadata:
  category: ci
  capabilities:
    - ci
  permissions:
    - worktree_read
  scope: core
---

# Ci Gates

Required checks bind the exact head SHA. Labels never satisfy merge. Reviewer identity is the gate.
