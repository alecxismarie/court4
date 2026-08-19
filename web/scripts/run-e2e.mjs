import { spawn, spawnSync } from "node:child_process";
import http from "node:http";
import process from "node:process";

const host = "localhost";
const port = Number.parseInt(process.env.COURT4_E2E_PORT ?? "3002", 10);
const url = `http://${host}:${port}`;
const nextBin = "./node_modules/next/dist/bin/next";
const playwrightBin = "./node_modules/@playwright/test/cli.js";
const apiUrl = process.env.COURT4_E2E_API_URL;
const expectedDatabaseName = process.env.COURT4_E2E_DATABASE_NAME;
const isolationConfirmation = process.env.COURT4_E2E_ISOLATION_CONFIRMATION;

if (!apiUrl || !expectedDatabaseName || isolationConfirmation !== "court4-e2e-isolated") {
  throw new Error(
    "E2E safety refusal: set COURT4_E2E_API_URL, COURT4_E2E_DATABASE_NAME, and " +
      "COURT4_E2E_ISOLATION_CONFIRMATION=court4-e2e-isolated explicitly.",
  );
}
if (!/^court4_(test|e2e|validation)(?:_|$)/.test(expectedDatabaseName)) {
  throw new Error("E2E safety refusal: database name is not an approved disposable identity.");
}

const server = spawn(
  process.execPath,
  [nextBin, "dev", "--hostname", host, "--port", String(port)],
  {
    env: {
      ...process.env,
      COURT4_NEXT_DIST_DIR: process.env.COURT4_NEXT_DIST_DIR ?? ".next-e2e",
      NEXT_PUBLIC_COURT4_API_URL: apiUrl,
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

function verifyApiIsolation(timeoutMs = 10_000) {
  return new Promise((resolve, reject) => {
    const request = http.get(
      new URL("/api/v1/internal/test-database-identity", apiUrl),
      (response) => {
        let body = "";
        response.setEncoding("utf8");
        response.on("data", (chunk) => {
          body += chunk;
        });
        response.on("end", () => {
          try {
            const payload = JSON.parse(body);
            if (response.statusCode !== 200 || payload.database_name !== expectedDatabaseName) {
              reject(new Error("E2E safety refusal: API database identity does not match."));
              return;
            }
            resolve();
          } catch {
            reject(new Error("E2E safety refusal: API identity response is invalid."));
          }
        });
      },
    );
    request.on("error", () => reject(new Error("E2E safety refusal: isolated API unavailable.")));
    request.setTimeout(timeoutMs, () => request.destroy(new Error("E2E API preflight timed out.")));
  });
}

function runPlaywright() {
  const requestedTests = process.argv.slice(2);
  const child = spawn(process.execPath, [playwrightBin, "test", ...requestedTests], {
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
    await verifyApiIsolation();
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
