import { requestJson } from "@/lib/api/client";
import {
  type AnalysisHistoryResponse,
  type PlayHistoryResponse,
  analysisHistoryResponseSchema,
  playHistoryResponseSchema,
} from "@/lib/api/types";

export function getAnalysisHistory(
  options: { limit?: number; offset?: number } = {},
): Promise<AnalysisHistoryResponse> {
  const limit = options.limit ?? 100;
  const offset = options.offset ?? 0;
  return requestJson(
    `/api/v1/analyses?limit=${limit}&offset=${offset}`,
    analysisHistoryResponseSchema,
  );
}

export function getPlayHistory(recentLimit = 5): Promise<PlayHistoryResponse> {
  return requestJson(
    `/api/v1/play-history?recent_limit=${recentLimit}`,
    playHistoryResponseSchema,
  );
}
