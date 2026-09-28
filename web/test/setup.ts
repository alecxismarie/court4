import "@testing-library/jest-dom/vitest";
import { webcrypto } from "node:crypto";

// jsdom has no native modal implementation; browser tests cover focus trapping.
if (typeof HTMLDialogElement !== "undefined") {
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); };
}

// jsdom supplies crypto.getRandomValues but not the browser's SubtleCrypto.
Object.defineProperty(globalThis.crypto, "subtle", { value: webcrypto.subtle, configurable: true });

process.env.NEXT_PUBLIC_COURT4_API_URL = "http://localhost:8000";
process.env.NEXT_PUBLIC_COURT4_MAX_UPLOAD_BYTES = "1073741824";
process.env.NEXT_PUBLIC_COURT4_SUPPORTED_VIDEO_EXTENSIONS = ".mp4,.mov,.avi,.mkv";
