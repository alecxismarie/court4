export type PublicEnv = {
  apiUrl: string;
  maxUploadBytes: number;
  supportedVideoExtensions: readonly string[];
};

const DEFAULT_MAX_UPLOAD_BYTES = 1_073_741_824;
const DEFAULT_SUPPORTED_EXTENSIONS = [".mp4", ".mov", ".avi", ".mkv"] as const;

export function getPublicEnv(): PublicEnv {
  const apiUrl = process.env.NEXT_PUBLIC_COURT4_API_URL;
  if (!apiUrl) {
    throw new Error("NEXT_PUBLIC_COURT4_API_URL is required.");
  }

  let parsedUrl: URL;
  try {
    parsedUrl = new URL(apiUrl);
  } catch {
    throw new Error("NEXT_PUBLIC_COURT4_API_URL must be a valid URL.");
  }

  return {
    apiUrl: parsedUrl.toString().replace(/\/$/, ""),
    maxUploadBytes: parsePositiveInteger(
      process.env.NEXT_PUBLIC_COURT4_MAX_UPLOAD_BYTES,
      DEFAULT_MAX_UPLOAD_BYTES,
    ),
    supportedVideoExtensions: parseExtensions(
      process.env.NEXT_PUBLIC_COURT4_SUPPORTED_VIDEO_EXTENSIONS,
    ),
  };
}

function parsePositiveInteger(value: string | undefined, fallback: number): number {
  if (!value) {
    return fallback;
  }
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    throw new Error("NEXT_PUBLIC_COURT4_MAX_UPLOAD_BYTES must be a positive integer.");
  }
  return parsed;
}

function parseExtensions(value: string | undefined): readonly string[] {
  if (!value) {
    return DEFAULT_SUPPORTED_EXTENSIONS;
  }
  const extensions = value
    .split(",")
    .map((extension) => extension.trim().toLowerCase())
    .filter(Boolean)
    .map((extension) => (extension.startsWith(".") ? extension : `.${extension}`));

  if (extensions.length === 0) {
    throw new Error("NEXT_PUBLIC_COURT4_SUPPORTED_VIDEO_EXTENSIONS cannot be empty.");
  }
  return Array.from(new Set(extensions));
}
