---
name: skill-regression
description: Evaluate imported skills with regression prompts and keep failures quarantined.
license: AGPL-3.0-or-later
compatibility: kronos
allowed-tools: Read Write Grep
metadata:
  category: skills
  capabilities:
    - skills
    - regression
  permissions:
    - worktree_read
  scope: core
---

# Skill Regression

Run regression prompts and permission checks. Keep failures quarantined. Do not execute untrusted skill scripts during scan.
