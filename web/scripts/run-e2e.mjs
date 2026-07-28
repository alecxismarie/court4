import { spawn, spawnSync } from "node:child_process";
import http from "node:http";
import process from "node:process";

const host = "127.0.0.1";
const port = Number.parseInt(process.env.COURT4_E2E_PORT ?? "3002", 10);
const url = `http://${host}:${port}`;
const nextBin = "./node_modules/next/dist/bin/next";
const playwrightBin = "./node_modules/@playwright/test/cli.js";

const server = spawn(
  process.execPath,
  [nextBin, "dev", "--hostname", host, "--port", String(port)],
  {
    env: {
      ...process.env,
      COURT4_NEXT_DIST_DIR: process.env.COURT4_NEXT_DIST_DIR ?? ".next-e2e",
      NEXT_PUBLIC_COURT4_API_URL:
        process.env.NEXT_PUBLIC_COURT4_API_URL ?? "http://127.0.0.1:8000",
      NEXT_PUBLIC_COURT4_MAX_UPLOAD_BYTES:
        process.env.NEXT_PUBLIC_COURT4_MAX_UPLOAD_BYTES ?? "1073741824",
      NEXT_PUBLIC_COURT4_SUPPORTED_VIDEO_EXTENSIONS:
        process.env.NEXT_PUBLIC_COURT4_SUPPORTED_VIDEO_EXTENSIONS ??
        ".mp4,.mov,.avi,.mkv",
    },
    stdio: "inherit",
  },
);

let serverExitCode = null;
server.on("exit", (code) => {
  serverExitCode = code ?? 1;
});

function waitForServer(timeoutMs = 60_000) {
  const startedAt = Date.now();

  return new Promise((resolve, reject) => {
    const poll = () => {
      if (serverExitCode !== null) {
        reject(new Error(`Next dev server exited with code ${serverExitCode}.`));
        return;
      }

      const request = http.get(url, (response) => {
        response.resume();
        resolve();
      });

      request.on("error", () => {
        if (Date.now() - startedAt > timeoutMs) {
          reject(new Error(`Timed out waiting for ${url}.`));
          return;
        }
        setTimeout(poll, 500);
      });

      request.setTimeout(2_000, () => {
        request.destroy();
      });
    };

    poll();
  });
}

function runPlaywright() {
  const child = spawn(process.execPath, [playwrightBin, "test"], {
    env: {
      ...process.env,
      COURT4_E2E_EXTERNAL_SERVER: "1",
    },
    stdio: "inherit",
  });

  return new Promise((resolve) => {
    child.on("exit", (code, signal) => {
      resolve(signal ? 1 : code ?? 1);
    });
  });
}

function stopServer() {
  if (!server.pid || serverExitCode !== null) {
    return;
  }

  if (process.platform === "win32") {
    spawnSync("taskkill", ["/pid", String(server.pid), "/t", "/f"], {
      stdio: "ignore",
    });
    return;
  }

  server.kill("SIGTERM");
}

async function main() {
  let exitCode = 1;

  try {
    await waitForServer();
    exitCode = await runPlaywright();
  } catch (error) {
    console.error(error instanceof Error ? error.message : error);
  } finally {
    stopServer();
  }

  process.exit(exitCode);
}

process.on("SIGINT", () => {
  stopServer();
  process.exit(130);
});

process.on("SIGTERM", () => {
  stopServer();
  process.exit(143);
});

await main();
