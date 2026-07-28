import { expect, test } from "@playwright/test";

test("a valid profile photo over 1 MB is resized, previewed, and saved", async ({ page }) => {
  await page.goto("/player");

  const onePixelPng = Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
    "base64",
  );
  await page.getByLabel("Profile photo", { exact: true }).setInputFiles({
    name: "large-profile.png",
    mimeType: "image/png",
    buffer: Buffer.concat([onePixelPng, Buffer.alloc(1_100_000)]),
  });

  await expect(page.getByRole("button", { name: "Remove photo" })).toBeVisible();
  await expect(page.getByText("Change photo")).toBeVisible();
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByRole("status")).toHaveText("Profile saved.");

  const storedImage = await page.evaluate(() => {
    const value = window.localStorage.getItem("court4.playerProfile");
    return value ? JSON.parse(value).profileImageDataUrl : null;
  });
  expect(storedImage).toMatch(/^data:image\/(?:webp|png);base64,/);
  expect(storedImage.length).toBeLessThan(1_333_500);
});
