// SPDX-License-Identifier: AGPL-3.0-or-later

import { execFileSync } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test } from "@playwright/test";
import {
  E2E_FINAL_ANSWER,
  E2E_MOCK_PORT,
  E2E_README_BODY,
} from "../support/mockOpenAi";

test.describe.configure({ mode: "serial" });

test("connects a mock model, enrols a folder, chats, and uses Files and Terminal", async ({
  page,
}) => {
  test.setTimeout(240_000);
  const repo = mkdtempSync(join(tmpdir(), "kronos-e2e-repo-"));
  writeFileSync(join(repo, "README.md"), E2E_README_BODY);
  execFileSync("git", ["init"], { cwd: repo });
  execFileSync("git", ["config", "user.email", "e2e@kronos.test"], { cwd: repo });
  execFileSync("git", ["config", "user.name", "Kronos E2E"], { cwd: repo });
  execFileSync("git", ["add", "README.md"], { cwd: repo });
  execFileSync("git", ["commit", "-m", "init"], { cwd: repo });

  await page.addInitScript(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
  });
  await page.goto("/");
  await expect(page.getByText("Engine ready")).toBeVisible({ timeout: 120_000 });
  const connectGate = page.getByRole("heading", { name: "Connect a model" });
  await expect(connectGate.or(page.getByRole("heading", { name: "Ask Kronos" }))).toBeVisible({
    timeout: 30_000,
  });
  if (await connectGate.isVisible()) {
    await expect(page.getByText("Looking for a local model server.")).toHaveCount(0, {
      timeout: 15_000,
    });
    await page.getByLabel("API URL").fill(`http://127.0.0.1:${E2E_MOCK_PORT}/v1`);
    await page.getByLabel(/model id/i).fill("mock");
    await page.getByRole("button", { name: "Continue" }).click();
  }

  const embeddingsHeading = page.getByRole("heading", { name: /install local embeddings/i });
  const workspaceStep = page.getByRole("heading", { name: "Open a workspace" });
  const askHeading = page.getByRole("heading", { name: "Ask Kronos" });
  await expect(workspaceStep.or(askHeading)).toBeVisible({ timeout: 60_000 });
  if (await embeddingsHeading.isVisible()) {
    await expect(page.getByText(/local embeddings are ready/i)).toBeVisible({ timeout: 30_000 });
    await expect(workspaceStep.or(askHeading)).toBeVisible({ timeout: 30_000 });
  }
  if (await workspaceStep.isVisible()) {
    await page.getByRole("button", { name: "Skip for now" }).click();
  }
  await expect(askHeading).toBeVisible({ timeout: 30_000 });

  await page.getByRole("button", { name: "Workspaces" }).click();
  const repoCard = page.locator(".workspace-card").filter({
    has: page.locator(".workspace-card__meta", { hasText: repo }),
  });
  if ((await repoCard.count()) === 0) {
    await page.getByRole("button", { name: "Enable Kronos" }).click();
    await page.locator("#repo-folder").fill(repo);
    await expect(page.locator("#repo-folder")).toHaveValue(repo);
    await page.getByRole("button", { name: "Preview" }).click();
    await expect(page.getByText(/preview only/i)).toBeVisible({ timeout: 60_000 });
    await page.getByRole("button", { name: /^enrol$/i }).click();
    await expect(repoCard).toBeVisible({ timeout: 30_000 });
  }
  await expect(repoCard.locator(".workspace-card__status")).toHaveText("active", {
    timeout: 15_000,
  });

  await page.getByRole("button", { name: "Chat" }).click();
  await expect(page.getByPlaceholder(/type @ to mention a file/i)).toBeVisible({ timeout: 15_000 });
  await page.getByRole("textbox", { name: "Ask Kronos" }).fill("what is in README");
  await page.getByRole("button", { name: /^send$/i }).click();
  await expect(page.getByText("Read file · done")).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText(E2E_FINAL_ANSWER)).toBeVisible();
  await expect(page.getByText("No file changes in this workspace yet.")).toBeVisible();

  await page.getByRole("button", { name: "Files" }).click();
  await page.getByRole("treeitem", { name: "README.md" }).click();
  await expect(page.getByRole("textbox", { name: "README.md" })).toHaveValue(E2E_README_BODY);

  await page.getByRole("menuitem", { name: "View" }).click();
  await page.getByRole("menuitem", { name: /^terminal$/i }).click();
  await expect(page.getByRole("heading", { name: "Terminal" })).toBeVisible();
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  const xtermInput = page.getByRole("textbox", { name: "Terminal" });
  await xtermInput.focus();
  await xtermInput.pressSequentially("echo ok", { delay: 40 });
  await xtermInput.press("Enter");
  await expect(page.locator(".terminal-page__tty")).toHaveValue(/echo ok[\s\S]*\bok\b/, {
    timeout: 30_000,
  });
});
