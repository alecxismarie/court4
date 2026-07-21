import { z } from "zod";

import { getPublicEnv } from "@/lib/env";
import { apiErrorResponseSchema } from "@/lib/api/types";

export class Court4ApiError extends Error {
  readonly code: string;
  readonly status: number | null;

  constructor(message: string, options: { code: string; status?: number | null }) {
    super(message);
    this.name = "Court4ApiError";
    this.code = options.code;
    this.status = options.status ?? null;
  }
}

export function normalizeApiError(error: unknown): Court4ApiError {
  if (error instanceof Court4ApiError) {
    return error;
  }
  if (error instanceof z.ZodError) {
    return new Court4ApiError("Court4 returned an unexpected response.", {
      code: "malformed_response",
    });
  }
  if (error instanceof TypeError) {
    return new Court4ApiError("Court4 backend is unavailable.", {
      code: "backend_unavailable",
    });
  }
  if (error instanceof Error) {
    return new Court4ApiError(error.message, { code: "unexpected_error" });
  }
  return new Court4ApiError("Unexpected frontend error.", { code: "unexpected_error" });
}

export async function requestJson<TResponse>(
  path: string,
  schema: z.ZodType<TResponse>,
): Promise<TResponse> {
  const response = await fetch(toApiUrl(path), {
    headers: { Accept: "application/json" },
  });

  if (!response.ok) {
    throw await apiErrorFromResponse(response);
  }

  const payload: unknown = await response.json();
  return schema.parse(payload);
}

export async function postJson<TResponse>(
  path: string,
  schema: z.ZodType<TResponse>,
  body?: unknown,
): Promise<TResponse> {
  const response = await fetch(toApiUrl(path), {
    method: "POST",
    headers:
      body === undefined
        ? { Accept: "application/json" }
        : { Accept: "application/json", "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (!response.ok) {
    throw await apiErrorFromResponse(response);
  }

  const payload: unknown = await response.json();
  return schema.parse(payload);
}

export function toApiUrl(path: string): string {
  const { apiUrl } = getPublicEnv();
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${apiUrl}${normalizedPath}`;
}

export function getArtifactUrl(analysisId: string, artifactPath: string): string {
  const encodedAnalysisId = encodeURIComponent(analysisId);
  const encodedArtifactPath = artifactPath
    .split("/")
    .map((part) => encodeURIComponent(part))
    .join("/");
  return toApiUrl(`/api/v1/analyses/${encodedAnalysisId}/artifacts/${encodedArtifactPath}`);
}

export async function apiErrorFromResponse(response: Response): Promise<Court4ApiError> {
  const fallback = new Court4ApiError(defaultStatusMessage(response.status), {
    code: `http_${response.status}`,
    status: response.status,
  });

  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    return fallback;
  }

  try {
    const payload: unknown = await response.json();
    const parsed = apiErrorResponseSchema.safeParse(payload);
    if (!parsed.success) {
      return fallback;
    }
    return new Court4ApiError(parsed.data.error.message, {
      code: parsed.data.error.code,
      status: response.status,
    });
  } catch {
    return fallback;
  }
}

function defaultStatusMessage(status: number): string {
  if (status === 404) {
    return "The requested analysis or artifact was not found.";
  }
  if (status === 409) {
    return "This analysis is not ready for that step yet.";
  }
  if (status === 413) {
    return "The selected video is larger than the upload limit.";
  }
  if (status >= 500) {
    return "Court4 hit an unexpected server error.";
  }
  return "Court4 could not process the request.";
}
