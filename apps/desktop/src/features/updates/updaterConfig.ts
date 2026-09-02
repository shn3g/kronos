// SPDX-License-Identifier: AGPL-3.0-or-later

/**
 * Mirrors `plugins.updater.pubkey` in tauri.conf.json.
 * Tests pass an empty string to cover the unsigned fail-closed state.
 */
export const UPDATER_PUBKEY =
  "dW50cnVzdGVkIGNvbW1lbnQ6IG1pbmlzaWduIHB1YmxpYyBrZXk6IEZCQkE2MjVEQjlGNDFDNEMKUldSTUhQUzVYV0s2KzNaSGlJSDVnakVTM3RJVml3K2dFSjZHQ1dYSFlMSUdwQ21SNUE2eVFDR3MK";

export function isUpdaterSigningConfigured(pubkey: string = UPDATER_PUBKEY): boolean {
  return pubkey.trim().length > 0;
}
