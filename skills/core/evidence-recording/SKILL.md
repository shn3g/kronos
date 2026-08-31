---
name: evidence-recording
description: Store reproductions, logs, and SHAs as readable artifacts.
license: AGPL-3.0-or-later
compatibility: kronos
allowed-tools: Read Write Grep
metadata:
  category: memory
  capabilities:
    - evidence
  permissions:
    - worktree_read
    - worktree_write
  scope: core
---

# Evidence Recording

Record reproductions, command results, and source SHAs. Do not store hidden chain-of-thought or secrets as memory.
