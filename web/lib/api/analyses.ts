import { z } from "zod";

import {
  Court4ApiError,
  apiErrorFromResponse,
  authenticatedFetch,
  getAccessToken,
  normalizeApiError,
  postJson,
  refreshAccessToken,
  requestJson,
  toApiUrl,
} from "@/lib/api/client";
import {
  type AnalysisJob,
  type AnalyticsGenerationResponse,
  type AnalyticsResponse,
  type CalibrationRequest,
  type CalibrationResponse,
  type CourtDetectionResponse,
  type UploadAnalysisResponse,
  type PlayerSelectionResponse,
  type PlayerCandidateCollection,
  type PlayersResponse,
  type SampledFramesResponse,
  type SportType,
  type TrackingRequest,
  type TrackingResponse,
  type UploadProgress,
  type PresignedUploadPart,
  analyticsGenerationResponseSchema,
  analyticsResponseSchema,
  analysisJobSchema,
  initiateUploadResponseSchema,
  uploadAnalysisResponseSchema,
  calibrationResponseSchema,
  courtDetectionResponseSchema,
  playerSelectionResponseSchema,
  playerCandidateCollectionSchema,
  playersResponseSchema,
  sampledFramesResponseSchema,
  trackingResponseSchema,
  uploadPartUrlResponseSchema,
  uploadSessionResponseSchema,
} from "@/lib/api/types";

export class TerminalUploadError extends Court4ApiError {}

export function createAnalysis(
  file: File,
  onProgress?: (progress: UploadProgress) => void,
  options?: {
    idempotencyKey?: string;
    reanalyze?: boolean;
    sport?: SportType;
    signal?: AbortSignal;
    onSession?: (sessionId: string) => void;
  },
): Promise<UploadAnalysisResponse> {
  return createAnalysisDirect(file, onProgress, options);
}

async function createAnalysisDirect(
  file: File,
  onProgress?: (progress: UploadProgress) => void,
  options?: {
    idempotencyKey?: string;
    reanalyze?: boolean;
    sport?: SportType;
    signal?: AbortSignal;
    onSession?: (sessionId: string) => void;
  },
): Promise<UploadAnalysisResponse> {
  const idempotencyKey = options?.idempotencyKey ?? crypto.randomUUID();
  throwIfAborted(options?.signal);
  const initiatedResponse = await authenticatedFetch(toApiUrl("/api/v1/uploads/initiate"), {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "Idempotency-Key": idempotencyKey,
    },
    body: JSON.stringify({
      filename: file.name,
      content_type: file.type || "application/octet-stream",
      byte_size: file.size,
      sport: options?.sport ?? "pickleball",
      reanalyze: options?.reanalyze ?? false,
    }),
    signal: options?.signal,
  });
  if (!initiatedResponse.ok) {
    throw await apiErrorFromResponse(initiatedResponse);
  }
  const initiated = initiateUploadResponseSchema.parse(await initiatedResponse.json());
  if (initiated.transport === "proxy") {
    return createAnalysisProxy(file, onProgress, { ...options, idempotencyKey });
  }
  if (!initiated.upload_session_id || !initiated.part_size) {
    throw new Court4ApiError("Court4 returned incomplete direct-upload instructions.", {
      code: "invalid_upload_session",
    });
  }

  const sessionId = initiated.upload_session_id;
  options?.onSession?.(sessionId);
  if (initiated.status === "completed") {
    return waitForUploadResult(sessionId, file, onProgress, options?.signal);
  }
  if (!["initiated", "uploading"].includes(initiated.status)) {
    return waitForUploadResult(sessionId, file, onProgress, options?.signal);
  }

  const transferController = new AbortController();
  const cancelTransfer = () => transferController.abort();
  options?.signal?.addEventListener("abort", cancelTransfer, { once: true });
  if (options?.signal?.aborted) cancelTransfer();
  try {
    const completedParts = await uploadParts({
      file,
      sessionId,
      initialParts: initiated.parts,
      partSize: initiated.part_size,
      concurrency: initiated.max_concurrency,
      maxAttempts: initiated.max_attempts,
      onProgress,
      signal: transferController.signal,
    });
    onProgress?.({
      loaded: file.size,
      total: file.size,
      percent: 100,
      phase: "verifying",
    });
    const completion = await authenticatedFetch(
      toApiUrl(`/api/v1/uploads/${encodeURIComponent(sessionId)}/complete`),
      {
        method: "POST",
        headers: { Accept: "application/json", "Content-Type": "application/json" },
        body: JSON.stringify({ parts: completedParts }),
        signal: options?.signal,
      },
    );
    if (!completion.ok) {
      throw await apiErrorFromResponse(completion);
    }
    const status = uploadSessionResponseSchema.parse(await completion.json());
    if (status.status === "completed" && status.result) {
      return status.result;
    }
    return await waitForUploadResult(sessionId, file, onProgress, options?.signal);
  } catch (error) {
    transferController.abort();
    const aborted = await abortDirectUpload(sessionId);
    const normalized = normalizeDirectUploadError(error);
    if (aborted) {
      throw new TerminalUploadError(normalized.message, normalized);
    }
    throw normalized;
  } finally {
    options?.signal?.removeEventListener("abort", cancelTransfer);
  }
}

function createAnalysisProxy(
  file: File,
  onProgress?: (progress: UploadProgress) => void,
  options?: {
    idempotencyKey?: string;
    reanalyze?: boolean;
    sport?: SportType;
    signal?: AbortSignal;
  },
): Promise<UploadAnalysisResponse> {
  return new Promise((resolve, reject) => {
    const idempotencyKey = options?.idempotencyKey ?? crypto.randomUUID();

    function sendAttempt(canRefresh: boolean) {
      const xhr = new XMLHttpRequest();
      const formData = new FormData();
      formData.append("file", file);
      formData.append("sport", options?.sport ?? "pickleball");
      if (options?.reanalyze) {
        formData.append("reanalyze", "true");
      }

      xhr.upload.addEventListener("progress", (event) => {
        if (!onProgress) {
          return;
        }
        const total = event.lengthComputable ? event.total : null;
        onProgress({
          loaded: event.loaded,
          total,
          percent: total ? Math.round((event.loaded / total) * 100) : null,
          phase: "uploading",
        });
      });

      xhr.addEventListener("load", () => {
        if (xhr.status === 401 && canRefresh) {
          void refreshAccessToken()
            .then(() => sendAttempt(false))
            .catch((error) => reject(normalizeApiError(error)));
          return;
        }
        if (xhr.status < 200 || xhr.status >= 300) {
          reject(errorFromXhr(xhr));
          return;
        }

        try {
          const payload: unknown = JSON.parse(xhr.responseText);
          resolve(uploadAnalysisResponseSchema.parse(payload));
        } catch (error) {
          reject(normalizeApiError(error));
        }
      });

      xhr.addEventListener("error", () => {
        reject(
          new Court4ApiError("Court4 backend is unavailable.", {
            code: "backend_unavailable",
          }),
        );
      });

      xhr.addEventListener("abort", () => {
        reject(new Court4ApiError("Upload was canceled.", { code: "upload_canceled" }));
      });

      const abort = () => xhr.abort();
      options?.signal?.addEventListener("abort", abort, { once: true });
      xhr.addEventListener("loadend", () => options?.signal?.removeEventListener("abort", abort));

      xhr.open("POST", toApiUrl("/api/v1/analyses"));
      xhr.withCredentials = true;
      xhr.setRequestHeader("Accept", "application/json");
      const accessToken = getAccessToken();
      if (accessToken) {
        xhr.setRequestHeader("Authorization", `Bearer ${accessToken}`);
      }
      xhr.setRequestHeader("Idempotency-Key", idempotencyKey);
      xhr.send(formData);
    }

    sendAttempt(true);
  });
}

type CompletedPart = { part_number: number; etag: string };

async function uploadParts({
  file,
  sessionId,
  initialParts,
  partSize,
  concurrency,
  maxAttempts,
  onProgress,
  signal,
}: {
  file: File;
  sessionId: string;
  initialParts: PresignedUploadPart[];
  partSize: number;
  concurrency: number;
  maxAttempts: number;
  onProgress?: (progress: UploadProgress) => void;
  signal?: AbortSignal;
}): Promise<CompletedPart[]> {
  const urls = new Map(initialParts.map((part) => [part.part_number, part.url]));
  const partCount = Math.ceil(file.size / partSize);
  if (urls.size !== partCount) {
    throw new Court4ApiError("Court4 returned an incomplete multipart upload plan.", {
      code: "missing_upload_part_url",
    });
  }
  const loadedByPart = new Map<number, number>();
  const results: CompletedPart[] = [];
  let nextPart = 1;

  const reportProgress = () => {
    if (signal?.aborted) return;
    const loaded = [...loadedByPart.values()].reduce((sum, value) => sum + value, 0);
    onProgress?.({
      loaded,
      total: file.size,
      percent: Math.min(100, Math.round((loaded / file.size) * 100)),
      phase: "uploading",
    });
  };

  const worker = async () => {
    while (nextPart <= partCount) {
      const partNumber = nextPart++;
      const start = (partNumber - 1) * partSize;
      const body = file.slice(start, Math.min(start + partSize, file.size));
      let lastError: unknown;
      for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
        throwIfAborted(signal);
        loadedByPart.set(partNumber, 0);
        try {
          let url = urls.get(partNumber);
          if (!url || (attempt > 1 && isAuthorizationFailure(lastError))) {
            url = await refreshPartUrl(sessionId, partNumber, signal);
            urls.set(partNumber, url);
          }
          const etag = await uploadPart(url, body, signal, (loaded) => {
            loadedByPart.set(partNumber, loaded);
            reportProgress();
          });
          loadedByPart.set(partNumber, body.size);
          results.push({ part_number: partNumber, etag });
          reportProgress();
          lastError = undefined;
          break;
        } catch (error) {
          lastError = error;
          if (attempt < maxAttempts) {
            await abortableDelay(250 * 2 ** (attempt - 1), signal);
          }
        }
      }
      if (lastError) {
        throw lastError;
      }
    }
  };

  await Promise.all(
    Array.from({ length: Math.min(Math.max(1, concurrency), partCount) }, () => worker()),
  );
  return results.sort((first, second) => first.part_number - second.part_number);
}

function uploadPart(
  url: string,
  body: Blob,
  signal: AbortSignal | undefined,
  onProgress: (loaded: number) => void,
): Promise<string> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const abort = () => xhr.abort();
    xhr.upload.addEventListener("progress", (event) => onProgress(event.loaded));
    xhr.addEventListener("load", () => {
      if (xhr.status < 200 || xhr.status >= 300) {
        reject(
          new Court4ApiError("A video part could not be uploaded to private storage.", {
            code: "upload_part_failed",
            status: xhr.status,
          }),
        );
        return;
      }
      const etag = xhr.getResponseHeader("ETag");
      if (!etag) {
        reject(
          new Court4ApiError("Private storage did not return the required upload receipt.", {
            code: "missing_upload_etag",
          }),
        );
        return;
      }
      resolve(etag);
    });
    xhr.addEventListener("error", () => {
      reject(
        new Court4ApiError("The storage provider could not receive a video part.", {
          code: "upload_provider_unreachable",
        }),
      );
    });
    xhr.addEventListener("abort", () => {
      reject(new Court4ApiError("Upload was canceled.", { code: "upload_canceled" }));
    });
    xhr.addEventListener("loadend", () => signal?.removeEventListener("abort", abort));
    signal?.addEventListener("abort", abort, { once: true });
    xhr.open("PUT", url);
    if (signal?.aborted) {
      signal.removeEventListener("abort", abort);
      reject(new Court4ApiError("Upload was canceled.", { code: "upload_canceled" }));
      return;
    }
    xhr.send(body);
  });
}

async function refreshPartUrl(
  sessionId: string,
  partNumber: number,
  signal?: AbortSignal,
): Promise<string> {
  const response = await authenticatedFetch(
    toApiUrl(`/api/v1/uploads/${encodeURIComponent(sessionId)}/parts`),
    {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify({ part_numbers: [partNumber] }),
      signal,
    },
  );
  if (!response.ok) throw await apiErrorFromResponse(response);
  const parsed = uploadPartUrlResponseSchema.parse(await response.json());
  const part = parsed.parts.find((candidate) => candidate.part_number === partNumber);
  if (!part) {
    throw new Court4ApiError("Court4 did not refresh the requested upload part.", {
      code: "missing_upload_part_url",
    });
  }
  return part.url;
}

async function waitForUploadResult(
  sessionId: string,
  file: File,
  onProgress?: (progress: UploadProgress) => void,
  signal?: AbortSignal,
): Promise<UploadAnalysisResponse> {
  onProgress?.({ loaded: file.size, total: file.size, percent: 100, phase: "verifying" });
  while (true) {
    throwIfAborted(signal);
    const response = await authenticatedFetch(
      toApiUrl(`/api/v1/uploads/${encodeURIComponent(sessionId)}`),
      { headers: { Accept: "application/json" }, signal },
    );
    if (!response.ok) throw await apiErrorFromResponse(response);
    const status = uploadSessionResponseSchema.parse(await response.json());
    if (status.status === "completed" && status.result) return status.result;
    if (["failed", "aborted", "expired"].includes(status.status)) {
      throw uploadTerminalError(status.status, status.failure_code);
    }
    await abortableDelay(1_000, signal);
  }
}

export async function abortDirectUpload(sessionId: string): Promise<boolean> {
  try {
    const response = await authenticatedFetch(toApiUrl(`/api/v1/uploads/${encodeURIComponent(sessionId)}`), {
      method: "DELETE",
      headers: { Accept: "application/json" },
      signal: AbortSignal.timeout(10_000),
    });
    return response.ok;
  } catch {
    // Admission reconciliation remains authoritative if this request cannot finish.
    return false;
  }
}

function uploadTerminalError(status: string, failureCode: string | null): Court4ApiError {
  if (status === "aborted") {
    return new TerminalUploadError("Upload was canceled.", { code: "upload_canceled" });
  }
  if (status === "expired") {
    return new TerminalUploadError("The upload session expired. Please start the upload again.", {
      code: "upload_session_expired",
    });
  }
  if (failureCode === "checksum_mismatch") {
    return new TerminalUploadError("The uploaded video failed integrity verification.", {
      code: "checksum_mismatch",
    });
  }
  return new TerminalUploadError("Court4 could not verify and finalize the uploaded video.", {
    code: failureCode ?? "upload_verification_failed",
  });
}

function normalizeDirectUploadError(error: unknown): Court4ApiError {
  if (error instanceof DOMException && error.name === "AbortError") {
    return new Court4ApiError("Upload was canceled.", { code: "upload_canceled" });
  }
  return normalizeApiError(error);
}

function isAuthorizationFailure(error: unknown): boolean {
  return error instanceof Court4ApiError && [401, 403].includes(error.status ?? 0);
}

function throwIfAborted(signal?: AbortSignal): void {
  if (signal?.aborted) throw new DOMException("Upload aborted", "AbortError");
}

function abortableDelay(milliseconds: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("Upload aborted", "AbortError"));
      return;
    }
    const finish = () => {
      signal?.removeEventListener("abort", abort);
      resolve();
    };
    const timeout = window.setTimeout(finish, milliseconds);
    const abort = () => {
      window.clearTimeout(timeout);
      reject(new DOMException("Upload aborted", "AbortError"));
    };
    signal?.addEventListener("abort", abort, { once: true });
  });
}

export function getAnalysis(analysisId: string): Promise<AnalysisJob> {
  return requestJson(
    `/api/v1/analyses/${encodeURIComponent(analysisId)}`,
    analysisJobSchema,
  );
}

export function getAnalysisFrames(analysisId: string): Promise<SampledFramesResponse> {
  return requestJson(
    `/api/v1/analyses/${encodeURIComponent(analysisId)}/frames`,
    sampledFramesResponseSchema,
  );
}

export function detectCourt(analysisId: string): Promise<CourtDetectionResponse> {
  return postJson(
    `/api/v1/analyses/${encodeURIComponent(analysisId)}/court-detection`,
    courtDetectionResponseSchema,
  );
}

export function submitCalibration(
  analysisId: string,
  request: CalibrationRequest,
): Promise<CalibrationResponse> {
  return postJson(
    `/api/v1/analyses/${encodeURIComponent(analysisId)}/calibration`,
    calibrationResponseSchema,
    request,
  );
}

export function startTracking(
  analysisId: string,
  request: TrackingRequest,
): Promise<TrackingResponse> {
  return postJson(
    `/api/v1/analyses/${encodeURIComponent(analysisId)}/tracking`,
    trackingResponseSchema,
    request,
  );
}

export function getPlayers(analysisId: string): Promise<PlayersResponse> {
  return requestJson(
    `/api/v1/analyses/${encodeURIComponent(analysisId)}/players`,
    playersResponseSchema,
  );
}

export function selectPlayer(
  analysisId: string,
  trackId: number,
): Promise<PlayerSelectionResponse> {
  return postJson(
    `/api/v1/analyses/${encodeURIComponent(analysisId)}/players/select`,
    playerSelectionResponseSchema,
    { track_id: trackId },
  );
}

export function getPlayerCandidates(analysisId: string): Promise<PlayerCandidateCollection> {
  return requestJson(
    `/api/v1/analyses/${encodeURIComponent(analysisId)}/player-candidates`,
    playerCandidateCollectionSchema,
  );
}

export function selectPlayerCandidate(
  analysisId: string,
  candidateId: string,
): Promise<PlayerCandidateCollection> {
  return postJson(
    `/api/v1/analyses/${encodeURIComponent(analysisId)}/player-candidates/${encodeURIComponent(candidateId)}/select`,
    playerCandidateCollectionSchema,
  );
}

export function rejectPlayerCandidate(
  analysisId: string,
  candidateId: string,
  reason = "not_a_player",
): Promise<PlayerCandidateCollection> {
  return postJson(
    `/api/v1/analyses/${encodeURIComponent(analysisId)}/player-candidates/${encodeURIComponent(candidateId)}/reject`,
    playerCandidateCollectionSchema,
    { reason },
  );
}

export function restorePlayerCandidate(
  analysisId: string,
  candidateId: string,
): Promise<PlayerCandidateCollection> {
  return postJson(
    `/api/v1/analyses/${encodeURIComponent(analysisId)}/player-candidates/${encodeURIComponent(candidateId)}/restore`,
    playerCandidateCollectionSchema,
  );
}

export function mergePlayerCandidates(
  analysisId: string,
  candidateIds: [string, string],
): Promise<PlayerCandidateCollection> {
  return postJson(
    `/api/v1/analyses/${encodeURIComponent(analysisId)}/player-candidates/merge`,
    playerCandidateCollectionSchema,
    { candidate_ids: candidateIds },
  );
}

export function unmergePlayerCandidate(
  analysisId: string,
  candidateId: string,
): Promise<PlayerCandidateCollection> {
  return postJson(
    `/api/v1/analyses/${encodeURIComponent(analysisId)}/player-candidates/unmerge`,
    playerCandidateCollectionSchema,
    { candidate_id: candidateId },
  );
}

export function generateAnalytics(analysisId: string): Promise<AnalyticsGenerationResponse> {
  return postJson(
    `/api/v1/analyses/${encodeURIComponent(analysisId)}/analytics`,
    analyticsGenerationResponseSchema,
  );
}

export function getAnalytics(analysisId: string): Promise<AnalyticsResponse> {
  return requestJson(
    `/api/v1/analyses/${encodeURIComponent(analysisId)}/analytics`,
    analyticsResponseSchema,
  );
}

function errorFromXhr(xhr: XMLHttpRequest): Court4ApiError {
  const parsed = parseErrorResponseText(xhr.responseText);
  if (parsed) {
    return new Court4ApiError(parsed.message, {
      code: parsed.code,
      status: xhr.status,
    });
  }
  return new Court4ApiError(statusMessage(xhr.status), {
    code: `http_${xhr.status}`,
    status: xhr.status,
  });
}

function parseErrorResponseText(value: string): { code: string; message: string } | null {
  try {
    const payload: unknown = JSON.parse(value);
    const parsed = z
      .object({ error: z.object({ code: z.string(), message: z.string() }) })
      .safeParse(payload);
    return parsed.success ? parsed.data.error : null;
  } catch {
    return null;
  }
}

function statusMessage(status: number): string {
  if (status === 400) {
    return "The selected video could not be uploaded.";
  }
  if (status === 413) {
    return "The selected video is larger than the upload limit.";
  }
  if (status >= 500) {
    return "Court4 hit an unexpected server error.";
  }
  return "Court4 could not process the upload.";
}

export async function normalizeFetchError(response: Response): Promise<Court4ApiError> {
  return apiErrorFromResponse(response);
}
