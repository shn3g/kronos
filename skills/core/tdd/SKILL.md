---
name: tdd
description: Write a failing test before implementation for behavior changes and bug fixes.
license: AGPL-3.0-or-later
compatibility: kronos
allowed-tools: Read Write Grep
metadata:
  category: testing
  capabilities:
    - tdd
    - write_tests
  permissions:
    - worktree_read
    - worktree_write
  scope: core
---

# Tdd

Write a failing test before implementation. Do not skip the red step. Implementation comes after the test fails.
