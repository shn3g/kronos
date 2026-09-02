// SPDX-License-Identifier: AGPL-3.0-or-later

/**
 * Must stay identical to `plugins.updater.pubkey` in tauri.conf.json.
 * Empty until the publisher keypair is in GitHub secrets and this value is replaced.
 */
export const UPDATER_PUBKEY = "";

export function isUpdaterSigningConfigured(pubkey: string = UPDATER_PUBKEY): boolean {
  return pubkey.trim().length > 0;
}
