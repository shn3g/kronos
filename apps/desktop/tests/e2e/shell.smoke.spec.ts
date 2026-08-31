import { expect, test } from "@playwright/test";

test("web shell shows engine unavailable and primary routes", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("status")).toContainText("Engine unavailable");
  await expect(page.getByText("Engine ready")).toHaveCount(0);
  await expect(page.getByRole("heading", { level: 1, name: "Home" })).toBeVisible();

  await page.getByRole("link", { name: "Workspaces" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Workspaces" })).toBeVisible();
  await expect(page.getByText(/connect a compatible engine to enrol repositories/i)).toBeVisible();
  await expect(page.getByRole("button", { name: /enable kronos/i })).toHaveCount(0);
  await page.getByRole("link", { name: "Models" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Models" })).toBeVisible();
  await expect(
    page.getByText(/connect a compatible engine to assign model profiles/i),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: /save assignments/i })).toHaveCount(0);
  await page.getByRole("link", { name: "Index" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Index" })).toBeVisible();
  await expect(
    page.getByText(/connect a compatible engine to inspect repository indexes/i),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: /rebuild index/i })).toHaveCount(0);
  await page.getByRole("link", { name: "Goals" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Goals" })).toBeVisible();
  await expect(
    page.getByText(/connect a compatible engine to create and track bounded goals/i),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: /create goal/i })).toHaveCount(0);
  await page.getByRole("link", { name: "Runs" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Runs" })).toBeVisible();
  await expect(
    page.getByText(/connect a compatible engine to inspect task runs/i),
  ).toBeVisible();
  await expect(page.getByRole("status")).toContainText("Engine unavailable");
});
