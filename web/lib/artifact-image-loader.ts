import { apiErrorFromResponse, authenticatedFetch } from "@/lib/api/client";

// Small private image reads share the staging workspace's single active slot.
// Keep the slot until the body is consumed, including bounded capacity retries.
const MAX_ATTEMPTS = 4;
const MAX_RETRY_DELAY_MS = 30_000;
const pending: Array<() => void> = [];
let active = false;

function drain() {
  if (!active) pending.shift()?.();
}

export function loadArtifactImage(src: string, signal: AbortSignal): Promise<Blob> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(signal.reason);
      return;
    }
    const cancelQueued = () => {
      const index = pending.indexOf(run);
      if (index !== -1) pending.splice(index, 1);
      reject(signal.reason);
    };
    const run = () => {
      signal.removeEventListener("abort", cancelQueued);
      active = true;
      fetchImage(src, signal).then(resolve, reject).finally(() => {
        active = false;
        drain();
      });
    };
    signal.addEventListener("abort", cancelQueued, { once: true });
    pending.push(run);
    drain();
  });
}

async function fetchImage(src: string, signal: AbortSignal): Promise<Blob> {
  for (let attempt = 1; ; attempt += 1) {
    signal.throwIfAborted();
    const response = await authenticatedFetch(src, { signal, headers: { Accept: "image/*" } });
    signal.throwIfAborted();
    if (response.ok) return response.blob();
    const error = await apiErrorFromResponse(response);
    if (response.status !== 429 || error.code !== "processing_workspace_unavailable" || attempt >= MAX_ATTEMPTS) {
      throw error;
    }
    const retryAfter = response.headers.get("Retry-After");
    const serverDelay = retryAfter === null ? 0 : /^\d+$/.test(retryAfter.trim())
      ? Number(retryAfter) * 1000
      : Math.max(0, Date.parse(retryAfter) - Date.now());
    const delay = Math.max(500 * 2 ** (attempt - 1), Number.isNaN(serverDelay) ? 0 : serverDelay);
    // Do not retry earlier than requested or hold the image queue indefinitely.
    if (delay > MAX_RETRY_DELAY_MS) throw error;
    await pause(delay, signal);
  }
}

function pause(milliseconds: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    signal.throwIfAborted();
    const cancel = () => {
      clearTimeout(timer);
      reject(signal.reason);
    };
    const timer = setTimeout(() => {
      signal.removeEventListener("abort", cancel);
      resolve();
    }, milliseconds);
    signal.addEventListener("abort", cancel, { once: true });
  });
}
