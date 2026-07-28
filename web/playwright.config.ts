import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  expect: {
    timeout: 7_500,
  },
  fullyParallel: false,
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:3002",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chrome",
      use: {
        ...devices["Desktop Chrome"],
        channel: process.env.COURT4_E2E_BROWSER_CHANNEL ?? "chrome",
      },
    },
  ],
  webServer:
    process.env.COURT4_E2E_EXTERNAL_SERVER === "1"
      ? undefined
      : {
          command:
            "node ./node_modules/next/dist/bin/next dev --hostname 127.0.0.1 --port 3002",
          url: "http://127.0.0.1:3002",
          reuseExistingServer: !process.env.CI,
          env: {
            COURT4_NEXT_DIST_DIR: ".next-e2e",
            NEXT_PUBLIC_COURT4_API_URL: "http://127.0.0.1:8000",
            NEXT_PUBLIC_COURT4_MAX_UPLOAD_BYTES: "1073741824",
            NEXT_PUBLIC_COURT4_SUPPORTED_VIDEO_EXTENSIONS: ".mp4,.mov,.avi,.mkv",
          },
        },
});
