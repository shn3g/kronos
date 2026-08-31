import { expect, test } from "@playwright/test";

test("web shell shows engine unavailable and primary routes", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("status")).toContainText("Engine unavailable");
  await expect(page.getByText("Engine ready")).toHaveCount(0);
  await expect(page.getByRole("heading", { level: 1, name: "Home" })).toBeVisible();

  await page.getByRole("link", { name: "Workspaces" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Workspaces" })).toBeVisible();
  await expect(page.getByRole("status")).toContainText("Engine unavailable");
});
