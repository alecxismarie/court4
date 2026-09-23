import { apiErrorFromResponse, authenticatedFetch, toApiUrl } from "@/lib/api/client";

export async function deleteSourceVideo(analysisId: string): Promise<void> {
  const response = await authenticatedFetch(
    toApiUrl(`/api/v1/analyses/${encodeURIComponent(analysisId)}/source-video`),
    { method: "DELETE", headers: { Accept: "application/json" } },
  );
  if (!response.ok) throw await apiErrorFromResponse(response);
}
