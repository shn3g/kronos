# Klikday example pack

This directory is the tested Kronos policy pack for the Klikday dashboard repository (`shn3g/klikday-dashboard`).

- `config.yaml` is schema 2. Integration stays `main-openclaw`. The protected default branch is `main`. Autonomy starts frozen in `shadow` mode.
- `lessons.yaml` is imported as disabled candidates. Import is not activation.

Copy `config.yaml` to `.kronos/config.yaml` in the enrolled repository. CODEOWNERS must cover `.kronos/**`. Do not put `coder_may_merge` or `pulse_may_merge` in this file. Those fuses are unrepresentable.

Kronos is the source of truth for automation going forward. Klikday `scripts/agent-ops` wrappers remain an operator fallback until two stable Kronos release cycles. Do not re-enable write crons from the contain change.
