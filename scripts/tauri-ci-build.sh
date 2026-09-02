#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Build desktop installers. When TAURI_SIGNING_PRIVATE_KEY is unset or empty,
# skip updater artifact signing so unsigned releases still produce installers.
# In-app Check for updates stays fail-closed until the owner installs a pubkey.
set -euo pipefail

if [ "${1:-}" = "" ]; then
  echo "usage: $0 <tauri-bundle-list>" >&2
  exit 2
fi

root="$(cd "$(dirname "$0")/.." && pwd)"
extra=()
if [ -z "${TAURI_SIGNING_PRIVATE_KEY:-}" ]; then
  unset TAURI_SIGNING_PRIVATE_KEY || true
  unset TAURI_SIGNING_PRIVATE_KEY_PASSWORD || true
  extra+=(--config '{"bundle":{"createUpdaterArtifacts":false}}')
fi

cd "$root/apps/desktop"
exec pnpm tauri build --bundles "$1" "${extra[@]}"
