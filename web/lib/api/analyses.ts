import { z } from "zod";

import {
  Court4ApiError,
  apiErrorFromResponse,
  normalizeApiError,
  postJson,
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
  type PlayerSelectionResponse,
  type PlayerCandidateCollection,
  type PlayersResponse,
  type SampledFramesResponse,
  type TrackingRequest,
  type TrackingResponse,
  type UploadProgress,
  analyticsGenerationResponseSchema,
  analyticsResponseSchema,
  analysisJobSchema,
  calibrationResponseSchema,
  courtDetectionResponseSchema,
  playerSelectionResponseSchema,
  playerCandidateCollectionSchema,
  playersResponseSchema,
  sampledFramesResponseSchema,
  trackingResponseSchema,
} from "@/lib/api/types";

export function createAnalysis(
  file: File,
  onProgress?: (progress: UploadProgress) => void,
): Promise<AnalysisJob> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const formData = new FormData();
    formData.append("file", file);

    xhr.upload.addEventListener("progress", (event) => {
      if (!onProgress) {
        return;
      }
      const total = event.lengthComputable ? event.total : null;
      onProgress({
        loaded: event.loaded,
        total,
        percent: total ? Math.round((event.loaded / total) * 100) : null,
      });
    });

    xhr.addEventListener("load", () => {
      if (xhr.status < 200 || xhr.status >= 300) {
        reject(errorFromXhr(xhr));
        return;
      }

      try {
        const payload: unknown = JSON.parse(xhr.responseText);
        resolve(analysisJobSchema.parse(payload));
      } catch (error) {
        reject(normalizeApiError(error));
      }
    });

    xhr.addEventListener("error", () => {
      reject(new Court4ApiError("Court4 backend is unavailable.", { code: "backend_unavailable" }));
    });

    xhr.addEventListener("abort", () => {
      reject(new Court4ApiError("Upload was canceled.", { code: "upload_canceled" }));
    });

    xhr.open("POST", toApiUrl("/api/v1/analyses"));
    xhr.setRequestHeader("Accept", "application/json");
    xhr.send(formData);
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
