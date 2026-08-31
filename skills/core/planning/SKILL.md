---
name: planning
description: Turn a goal into a bounded task graph with risk, WIP, and evidence.
license: AGPL-3.0-or-later
compatibility: kronos
allowed-tools: Read Write Grep
metadata:
  category: planning
  capabilities:
    - plan
  permissions:
    - worktree_read
  scope: core
---

# Planning

Produce a bounded task graph. Keep WIP limits. Raise risk only. Never shrink the size clamp.
