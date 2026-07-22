import type { AnalyticsReport, MatchIQReport } from "@/lib/api/types";

export type ShareCardFormatId = "story" | "portrait" | "square";

export type ShareCardFormat = {
  id: ShareCardFormatId;
  label: string;
  sizeLabel: string;
  width: number;
  height: number;
};

export type ShareCardArtifact = "heatmap" | "trajectory" | "none";

export type ShareCardData = {
  analysisId: string;
  playerName: string;
  matchDate?: string;
  totalDistance?: {
    value: number;
    unit: string;
  };
  zones?: {
    kitchen?: number;
    transition?: number;
    baseline?: number;
  };
  summary?: string;
  insights: Array<{
    title: string;
    statement: string;
  }>;
  focus?: string;
  artifactUrl?: string;
  artifactLabel?: string;
  resultsUrl?: string;
};

export const SHARE_CARD_FORMATS: ShareCardFormat[] = [
  {
    id: "story",
    label: "Story",
    sizeLabel: "Instagram Story 9:16",
    width: 1080,
    height: 1920,
  },
  {
    id: "portrait",
    label: "Portrait",
    sizeLabel: "Instagram/Facebook 4:5",
    width: 1080,
    height: 1350,
  },
  {
    id: "square",
    label: "Square",
    sizeLabel: "Square Post 1:1",
    width: 1080,
    height: 1080,
  },
];

export function getShareCardFormat(formatId: ShareCardFormatId): ShareCardFormat {
  return SHARE_CARD_FORMATS.find((format) => format.id === formatId) ?? SHARE_CARD_FORMATS[0];
}

export function buildShareCardData({
  analytics,
  matchIQ,
  playerName,
  artifact,
  resultsUrl,
}: {
  analytics: AnalyticsReport;
  matchIQ: MatchIQReport | null;
  playerName: string;
  artifact: ShareCardArtifact;
  resultsUrl?: string;
}): ShareCardData {
  const normalizedPlayerName = playerName.trim() || "Local Player";
  const artifactPath = getArtifactPath(analytics, artifact);

  return {
    analysisId: analytics.analysis_id,
    playerName: normalizedPlayerName,
    matchDate: formatShareDate(analytics.created_at),
    totalDistance: {
      value: analytics.distance.total_distance_feet,
      unit: "ft",
    },
    zones: {
      kitchen: analytics.zone_occupancy.kitchen.percentage,
      transition: analytics.zone_occupancy.transition_zone.percentage,
      baseline: analytics.zone_occupancy.baseline_area.percentage,
    },
    summary: matchIQ?.summary,
    insights:
      matchIQ?.status === "generated"
        ? matchIQ.insights.slice(0, 2).map((insight) => ({
            title: insight.title,
            statement: insight.statement,
          }))
        : [],
    focus: matchIQ?.focus
      ? `${matchIQ.focus.title}: ${matchIQ.focus.statement}`
      : undefined,
    artifactUrl: artifactPath
      ? getShareArtifactUrl(analytics.analysis_id, `analytics/${artifactPath.filename}`)
      : undefined,
    artifactLabel: artifactPath?.label,
    resultsUrl,
  };
}

export function getShareArtifactUrl(analysisId: string, artifactPath: string): string {
  const encodedAnalysisId = encodeURIComponent(analysisId);
  const encodedArtifactPath = artifactPath
    .split("/")
    .map((part) => encodeURIComponent(part))
    .join("/");
  return `/api/share-artifact/${encodedAnalysisId}/${encodedArtifactPath}`;
}

function getArtifactPath(
  analytics: AnalyticsReport,
  artifact: ShareCardArtifact,
): { filename: string; label: string } | null {
  if (artifact === "heatmap") {
    return { filename: analytics.artifacts.heatmap_png, label: "Heatmap" };
  }
  if (artifact === "trajectory") {
    return { filename: analytics.artifacts.trajectory_png, label: "Trajectory" };
  }
  return null;
}

function formatShareDate(value: string): string | undefined {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return undefined;
  }
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  }).format(date);
}
