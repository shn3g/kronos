---
name: issue-hygiene
description: Write GitHub issues and pull requests in the same plain-English format.
license: AGPL-3.0-or-later
compatibility: kronos
allowed-tools: Read Write Grep
metadata:
  category: git
  capabilities:
    - github
  permissions:
    - worktree_read
  scope: core
---

# Issue Hygiene

Use the same four headings for GitHub issues and pull requests: Scope, Acceptance criteria, Evidence, Out of scope. Write in plain English. Do not invent issues in observe or shadow mode. Apply `kronos:goal`, `kind:feature|fix|chore`, `size:XS`…`size:L`, and `risk:low`…`risk:critical` when the mode allows `create_issue` and the largest task is M or L.
