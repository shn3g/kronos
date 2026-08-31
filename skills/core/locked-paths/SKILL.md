---
name: locked-paths
description: Honor locked modules and the one-writer rule for contended paths.
license: AGPL-3.0-or-later
compatibility: kronos
allowed-tools: Read Write Grep
metadata:
  category: policy
  capabilities:
    - scope
  permissions:
    - worktree_read
  scope: core
---

# Locked Paths

Honor locked paths. One writer at a time. Do not edit modules locked to another task.
