import { chromium } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const baseUrl = process.env.COURT4_WEB_URL ?? "http://localhost:3000";
const chromePath =
  process.env.COURT4_CHROME_PATH ??
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const outputDirectory = path.resolve("artifacts", "landing");
const viewports = [
  { name: "desktop", width: 1440, height: 1000 },
  { name: "laptop", width: 1280, height: 800 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "mobile", width: 390, height: 844 },
];

await mkdir(outputDirectory, { recursive: true });
const browser = await chromium.launch({ executablePath: chromePath, headless: true });

try {
  for (const viewport of viewports) {
    const context = await browser.newContext({
      viewport: { width: viewport.width, height: viewport.height },
      deviceScaleFactor: 1,
      reducedMotion: "reduce",
    });
    const page = await context.newPage();
    const runtimeErrors = [];
    page.on("pageerror", (error) => runtimeErrors.push(error.message));
    await page.goto(baseUrl, { waitUntil: "networkidle" });
    await page.getByRole("heading", { name: /know your game/i }).waitFor();
    await page.screenshot({
      path: path.join(outputDirectory, `${viewport.name}.png`),
      fullPage: true,
    });
    const layout = await page.evaluate(() => ({
      clientWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
      pageHeight: document.documentElement.scrollHeight,
    }));
    process.stdout.write(
      `${viewport.name}: ${JSON.stringify(layout)} errors=${runtimeErrors.length}\n`,
    );
    if (runtimeErrors.length) {
      process.stdout.write(`${runtimeErrors.join("\n")}\n`);
      process.exitCode = 1;
    }
    if (layout.scrollWidth > layout.clientWidth) {
      process.stderr.write(`${viewport.name}: horizontal overflow detected\n`);
      process.exitCode = 1;
    }
    await context.close();
  }
} finally {
  await browser.close();
}
