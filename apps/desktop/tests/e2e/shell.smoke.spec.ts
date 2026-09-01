import { expect, test } from "@playwright/test";

test("web shell shows engine unavailable before the app chrome", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("status")).toContainText("Engine unavailable");
  await expect(page.getByText("Engine ready")).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: /local engine is not running/i }),
  ).toBeVisible();
  await expect(page.getByRole("textbox", { name: /ask kronos/i })).toHaveCount(0);
  await expect(page.getByText(/engineering OS/i)).toHaveCount(0);
});
