// SPDX-License-Identifier: AGPL-3.0-or-later

import { defineConfig, devices } from "@playwright/test";

const withEngine = process.env.KRONOS_E2E_ENGINE === "1";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: !withEngine,
  workers: withEngine ? 1 : undefined,
  timeout: withEngine ? 240_000 : 30_000,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? (withEngine ? 0 : 2) : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: withEngine ? "http://127.0.0.1:1420" : "http://127.0.0.1:4173",
    trace: "on-first-retry",
  },
  projects: withEngine
    ? [
        {
          name: "with-engine",
          testMatch: /with-engine\/.*\.spec\.ts/,
          use: { ...devices["Desktop Chrome"] },
        },
      ]
    : [
        {
          name: "chromium",
          testMatch: /shell\.smoke\.spec\.ts/,
          use: { ...devices["Desktop Chrome"] },
        },
      ],
  webServer: withEngine
    ? {
        command: "node --experimental-strip-types tests/e2e/support/startWithEngine.ts",
        url: "http://127.0.0.1:1420",
        reuseExistingServer: !process.env.CI,
        timeout: 180_000,
      }
    : {
        command: "pnpm build && pnpm preview",
        url: "http://127.0.0.1:4173",
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
      },
});
