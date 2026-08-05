import { expect, test } from "./fixtures";

test("verified private-alpha session restores and can log out", async ({ page, alphaUser }) => {
  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { name: /welcome/i })).toBeVisible();
  await page.reload();
  await expect(page).toHaveURL(/\/dashboard$/);
  await page.goto("/settings");
  await expect(page.getByText(alphaUser.email)).toBeVisible();
  await page.getByRole("button", { name: /log out/i }).click();
  await expect(page).toHaveURL(/\/?\?auth=login&next=%2Fsettings$/);
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/?\?auth=login&next=%2Fdashboard$/);
});

test("unauthenticated protected navigation is rejected", async ({ browser }) => {
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/?\?auth=login&next=%2Fdashboard/);
  await context.close();
});
