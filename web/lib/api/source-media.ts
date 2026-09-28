import { apiErrorFromResponse, authenticatedFetch, toApiUrl } from "@/lib/api/client";
import { requestJson } from "@/lib/api/client";
import { z } from "zod";

export function getMatchLifecycle(analysisId: string) {
  return requestJson(`/api/v1/analyses/${encodeURIComponent(analysisId)}/lifecycle`, z.object({
    analysis_id: z.string(), state: z.enum(["live", "deletion_pending", "deleted"]),
  }));
}

export async function deleteMatch(analysisId: string): Promise<void> {
  const response = await authenticatedFetch(toApiUrl(`/api/v1/analyses/${encodeURIComponent(analysisId)}`), { method: "DELETE" });
  if (!response.ok) throw await apiErrorFromResponse(response);
}

export async function deleteSourceVideo(analysisId: string): Promise<void> {
  const response = await authenticatedFetch(
    toApiUrl(`/api/v1/analyses/${encodeURIComponent(analysisId)}/source-video`),
    { method: "DELETE", headers: { Accept: "application/json" } },
  );
  if (!response.ok) throw await apiErrorFromResponse(response);
}
