import { z } from "zod";
import { fileIdentity } from "@/lib/file-identity";

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
  uploadRecoverySchema,
  type UploadRecovery,
} from "@/lib/api/types";

export class TerminalUploadError extends Court4ApiError {}

export type UploadOptions = {
  idempotencyKey?: string;
  reanalyze?: boolean;
  sport?: SportType;
  signal?: AbortSignal;
  onSession?: (sessionId: string) => void;
  resumeSessionId?: string;
};

export function discoverUploads(): Promise<UploadRecovery[]> {
  return requestJson("/api/v1/uploads/recoverable", z.array(uploadRecoverySchema));
}

export function recoverUpload(sessionId: string): Promise<UploadRecovery> {
  return requestJson(`/api/v1/uploads/${encodeURIComponent(sessionId)}/recovery`, uploadRecoverySchema);
}

export function createAnalysis(
  file: File,
  onProgress?: (progress: UploadProgress) => void,
  options?: UploadOptions,
): Promise<UploadAnalysisResponse> {
  return createAnalysisDirect(file, onProgress, options);
}

async function createAnalysisDirect(
  file: File,
  onProgress?: (progress: UploadProgress) => void,
  options?: UploadOptions,
): Promise<UploadAnalysisResponse> {
  const idempotencyKey = options?.idempotencyKey ?? crypto.randomUUID();
  throwIfAborted(options?.signal);
  const identity = await fileIdentity(file, options?.signal);
  if (options?.resumeSessionId) {
    const recovery = await postJson(`/api/v1/uploads/${encodeURIComponent(options.resumeSessionId)}/resume`,
      uploadRecoverySchema, { file_identity: identity, byte_size: file.size });
    return resumeTransfer(file, recovery, onProgress, options);
  }
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
      file_identity: identity,
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
  if (initiated.resumed) {
    const recovery = await recoverUpload(sessionId);
    return resumeTransfer(file, recovery, onProgress, options);
  }
  if (initiated.status === "completed") {
    return waitForUploadResult(sessionId, file, onProgress, options?.signal);
  }
  if (!["initiated", "uploading"].includes(initiated.status)) {
    return waitForUploadResult(sessionId, file, onProgress, options?.signal);
  }

  return transferDirect(file, sessionId, initiated.parts, [], initiated.part_size,
    initiated.max_concurrency, initiated.max_attempts, initiated.inactivity_seconds, onProgress, options);
}

function resumeTransfer(file: File, recovery: UploadRecovery, onProgress?: (p: UploadProgress) => void, options?: UploadOptions) {
  options?.onSession?.(recovery.upload_session_id);
  if (!["initiated", "uploading"].includes(recovery.status)) {
    return waitForUploadResult(recovery.upload_session_id, file, onProgress, options?.signal);
  }
  return transferDirect(file, recovery.upload_session_id, [], recovery.completed_parts,
    recovery.part_size, recovery.max_concurrency, recovery.max_attempts, recovery.inactivity_seconds,
    onProgress, options);
}

async function transferDirect(file: File, sessionId: string, initialParts: PresignedUploadPart[],
  existingParts: CompletedPart[], partSize: number, concurrency: number, maxAttempts: number,
  inactivitySeconds: number, onProgress?: (p: UploadProgress) => void, options?: UploadOptions,
): Promise<UploadAnalysisResponse> {
  const transferController = new AbortController();
  const cancelTransfer = () => transferController.abort();
  options?.signal?.addEventListener("abort", cancelTransfer, { once: true });
  if (options?.signal?.aborted) cancelTransfer();
  try {
    const completedParts = await uploadParts({
      file,
      sessionId,
      initialParts, existingParts, partSize, concurrency, maxAttempts, inactivitySeconds,
      onProgress,
      signal: transferController.signal,
    });
    return await completeDirectUpload(sessionId, completedParts, file.size, onProgress, options?.signal);
  } catch (error) {
    // Network/auth failures and unmounts pause transfers. Only an explicit user
    // cancellation may destroy the durable session and its completed parts.
    transferController.abort();
    throw normalizeDirectUploadError(error);
  } finally {
    options?.signal?.removeEventListener("abort", cancelTransfer);
  }
}

export async function completeDirectUpload(sessionId: string, completedParts: CompletedPart[],
  byteSize: number, onProgress?: (p: UploadProgress) => void, signal?: AbortSignal,
): Promise<UploadAnalysisResponse> {
    onProgress?.({ loaded: byteSize, total: byteSize, percent: 100, phase: "verifying" });
    const completion = await authenticatedFetch(
      toApiUrl(`/api/v1/uploads/${encodeURIComponent(sessionId)}/complete`),
      {
        method: "POST",
        headers: { Accept: "application/json", "Content-Type": "application/json" },
        body: JSON.stringify({ parts: completedParts }),
        signal,
      },
    );
    if (!completion.ok) {
      throw await apiErrorFromResponse(completion);
    }
    const status = uploadSessionResponseSchema.parse(await completion.json());
    if (status.status === "completed" && status.result) {
      return status.result;
    }
    return await waitForUploadResult(sessionId, { size: byteSize }, onProgress, signal);
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
  existingParts,
  inactivitySeconds,
  partSize,
  concurrency,
  maxAttempts,
  onProgress,
  signal,
}: {
  file: File;
  sessionId: string;
  initialParts: PresignedUploadPart[];
  existingParts: CompletedPart[];
  inactivitySeconds: number;
  partSize: number;
  concurrency: number;
  maxAttempts: number;
  onProgress?: (progress: UploadProgress) => void;
  signal?: AbortSignal;
}): Promise<CompletedPart[]> {
  const urls = new Map(initialParts.map((part) => [part.part_number, part]));
  const partCount = Math.ceil(file.size / partSize);
  const loadedByPart = new Map<number, number>();
  const results: CompletedPart[] = [...existingParts];
  const completed = new Set(existingParts.map((p) => p.part_number));
  for (const number of completed) loadedByPart.set(number, Math.min(partSize, file.size - (number - 1) * partSize));
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
      if (completed.has(partNumber)) continue;
      const start = (partNumber - 1) * partSize;
      const body = file.slice(start, Math.min(start + partSize, file.size));
      let lastError: unknown;
      for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
        throwIfAborted(signal);
        loadedByPart.set(partNumber, 0);
        reportProgress();
        try {
          let part = urls.get(partNumber);
          if (!part || Date.parse(part.expires_at) <= Date.now() + 30_000 ||
              (attempt > 1 && isAuthorizationFailure(lastError))) {
            part = await refreshPartUrl(sessionId, partNumber, signal);
            urls.set(partNumber, part);
          }
          const etag = await uploadPart(part.url, body, signal, inactivitySeconds, (loaded) => {
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
          loadedByPart.set(partNumber, 0);
          reportProgress();
          if (signal?.aborted || (error instanceof Court4ApiError && error.status === 401 &&
              error.code !== "upload_part_failed")) throw error;
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

  reportProgress();
  await Promise.all(
    Array.from({ length: Math.min(Math.max(1, concurrency), partCount) }, () => worker()),
  );
  return results.sort((first, second) => first.part_number - second.part_number);
}

function uploadPart(
  url: string,
  body: Blob,
  signal: AbortSignal | undefined,
  inactivitySeconds: number,
  onProgress: (loaded: number) => void,
): Promise<string> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    let watchdog: ReturnType<typeof setTimeout>;
    let lastLoaded = 0;
    let stalled = false;
    const armWatchdog = () => {
      clearTimeout(watchdog);
      watchdog = setTimeout(() => { stalled = true; xhr.abort(); }, inactivitySeconds * 1000);
    };
    const abort = () => xhr.abort();
    xhr.upload.addEventListener("progress", (event) => {
      if (event.loaded > lastLoaded) { lastLoaded = event.loaded; armWatchdog(); }
      onProgress(event.loaded);
    });
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
      reject(new Court4ApiError(stalled ? "A video part stopped responding. Please resume the upload." : "Upload interrupted. Your uploaded parts are preserved.",
        { code: stalled ? "upload_part_stalled" : "upload_canceled" }));
    });
    xhr.addEventListener("loadend", () => { clearTimeout(watchdog); signal?.removeEventListener("abort", abort); });
    signal?.addEventListener("abort", abort, { once: true });
    xhr.open("PUT", url);
    if (signal?.aborted) {
      signal.removeEventListener("abort", abort);
      reject(new Court4ApiError("Upload was canceled.", { code: "upload_canceled" }));
      return;
    }
    armWatchdog();
    xhr.send(body);
  });
}

async function refreshPartUrl(
  sessionId: string,
  partNumber: number,
  signal?: AbortSignal,
): Promise<PresignedUploadPart> {
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
  return part;
}

export async function waitForUploadResult(
  sessionId: string,
  file: Pick<File, "size">,
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
