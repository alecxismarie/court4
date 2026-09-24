// Matches stream_file_identity on the API. Hash every byte with fixed 8 MiB
// chunks instead of allocating an entire full-match video in browser memory.
export async function fileIdentity(file: File, signal?: AbortSignal): Promise<string> {
  const encoder = new TextEncoder();
  const prefix = encoder.encode("court4-file-v1\n");
  const suffix = encoder.encode(`\n${file.size}`);
  const count = Math.ceil(file.size / 8_388_608);
  const commitment = new Uint8Array(prefix.length + count * 32 + suffix.length);
  commitment.set(prefix);
  for (let index = 0; index < count; index += 1) {
    signal?.throwIfAborted();
    const bytes = await readBlob(file.slice(index * 8_388_608, (index + 1) * 8_388_608), signal);
    const digest = await crypto.subtle.digest("SHA-256", bytes);
    commitment.set(new Uint8Array(digest), prefix.length + index * 32);
  }
  signal?.throwIfAborted();
  commitment.set(suffix, prefix.length + count * 32);
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", commitment));
  return `sha256-chunks-v1:${Array.from(digest, (byte) => byte.toString(16).padStart(2, "0")).join("")}`;
}

function readBlob(blob: Blob, signal?: AbortSignal): Promise<ArrayBuffer> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    const abort = () => reader.abort();
    reader.onload = () => resolve(reader.result as ArrayBuffer);
    reader.onerror = () => reject(new Error("The selected video could not be read."));
    reader.onabort = () => reject(new DOMException("Upload paused", "AbortError"));
    reader.onloadend = () => signal?.removeEventListener("abort", abort);
    signal?.throwIfAborted();
    signal?.addEventListener("abort", abort, { once: true });
    reader.readAsArrayBuffer(blob);
  });
}
