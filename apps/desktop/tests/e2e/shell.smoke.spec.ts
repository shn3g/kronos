import { expect, test } from "@playwright/test";

test("web shell shows the engine gate and no menu bar", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "The local engine is not running" })).toBeVisible();
  await expect(page.getByRole("status")).toContainText("Engine unavailable");
  await expect(page.getByText("Engine ready")).toHaveCount(0);
  await expect(page.getByRole("menubar")).toHaveCount(0);
  await expect(page.getByRole("navigation", { name: /activity/i })).toHaveCount(0);
  await expect(page.getByRole("heading", { level: 1, name: "Home" })).toHaveCount(0);
});
