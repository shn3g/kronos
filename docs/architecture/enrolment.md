# Repository enrolment

Enable Kronos inspects a git folder, shows a preview of `.kronos/config.yaml`, `.github/workflows/kronos-pr.yml`, and CODEOWNERS, and registers the repository in SQLite. Generated files are preview-only. Runtime state and worktrees stay under application data and cache, not the enrolled working tree.

`GET /repositories` lists enrolled records. Isolation is by repository id: another id returns 404 and cannot read the first repository's policy.
