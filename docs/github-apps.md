# GitHub Apps

Kronos uses two GitHub Apps with separate identities.

## Controller

Opens draft pull requests to the integration branch. Stamps run provenance. Never posts the required reviewer check. Never merges the protected default branch.

Manifest template: `templates/github/controller-app-manifest.json`.

Private keys live in the OS secret store under `github:controller:private_key`. The worker environment does not receive this material.

## Reviewer

Isolated process (`services/reviewer`). Fetches the exact head and base. Loads `.kronos/config.yaml` from the **base** commit. Recalculates risk. Reruns required commands in a fresh sandbox. Publishes one check named `kronos-review (kronos-reviewer)` bound to the reviewer App id and the head SHA.

Manifest template: `templates/github/reviewer-app-manifest.json`.

Private keys live under `github:reviewer:private_key`. Ambient `GH_TOKEN` is not reviewer identity.

## Rulesets

Enrolment can propose a ruleset. It must require the reviewer check with `integration_id`, keep strict required status checks, and zero bypass actors. Kronos will not copy `strict_required_status_checks_policy: false`.

## Workflows

`templates/github/kronos-pr.yml` is the repository workflow template. CODEOWNERS must cover `.kronos/**` and that workflow. See `templates/github/CODEOWNERS`.

Kronos does not use Hermes check names.
