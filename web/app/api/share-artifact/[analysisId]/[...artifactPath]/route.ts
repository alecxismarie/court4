import { getPublicEnv } from "@/lib/env";

export const dynamic = "force-dynamic";

export async function GET(
  request: Request,
  {
    params,
  }: {
    params: { analysisId: string; artifactPath: string[] };
  },
) {
  const artifactPath = params.artifactPath.join("/");
  if (!isAllowedShareArtifact(artifactPath)) {
    return new Response("Share artifact not found.", { status: 404 });
  }

  const response = await fetch(toBackendArtifactUrl(params.analysisId, artifactPath), {
    headers: {
      Accept: "image/png",
      ...(request.headers.get("authorization")
        ? { Authorization: request.headers.get("authorization")! }
        : {}),
    },
    cache: "no-store",
  });

  if (!response.ok) {
    return new Response("Share artifact not found.", {
      status: response.status === 404 ? 404 : 502,
    });
  }

  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.startsWith("image/")) {
    return new Response("Share artifact is not an image.", { status: 415 });
  }

  return new Response(response.body, {
    status: 200,
    headers: {
      "Cache-Control": "no-store",
      "Content-Type": contentType,
    },
  });
}

function isAllowedShareArtifact(artifactPath: string): boolean {
  return /^analytics\/[^/]+\.png$/.test(artifactPath);
}

function toBackendArtifactUrl(analysisId: string, artifactPath: string): string {
  const { apiUrl } = getPublicEnv();
  const encodedAnalysisId = encodeURIComponent(analysisId);
  const encodedArtifactPath = artifactPath
    .split("/")
    .map((part) => encodeURIComponent(part))
    .join("/");
  return `${apiUrl}/api/v1/analyses/${encodedAnalysisId}/artifacts/${encodedArtifactPath}`;
}
