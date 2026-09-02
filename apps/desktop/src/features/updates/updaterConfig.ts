// SPDX-License-Identifier: AGPL-3.0-or-later

/**
 * Must stay identical to `plugins.updater.pubkey` in tauri.conf.json.
 */
export const UPDATER_PUBKEY =
  "dW50cnVzdGVkIGNvbW1lbnQ6IG1pbmlzaWduIHB1YmxpYyBrZXk6IEU5NjVGRDI4QjQ5M0ZFREMKUldUYy9wTzBLUDFsNlpTS1V0VER0MWluY2hOckZCcHBSK1Q4MGpyTXdvQitGbVNtOXk4ak1kRHUK";

export function isUpdaterSigningConfigured(pubkey: string = UPDATER_PUBKEY): boolean {
  return pubkey.trim().length > 0;
}
