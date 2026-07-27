import type { AnalysisJob, AnalyticsResponse } from "@/lib/api/types";

export type WorkspaceAnalysisRecord = {
  analysisId: string;
  job: AnalysisJob | null;
  analytics: AnalyticsResponse | null;
  jobError?: string | null;
  analyticsError?: string | null;
};

export type WorkspaceZoneSummary = {
  key: "kitchen" | "transition" | "baseline";
  label: string;
  percentage: number;
  seconds?: number;
};

export type WorkspaceSummary = {
  completedMatches: WorkspaceAnalysisRecord[];
  completedMatchCount: number;
  completedMatchIqCount: number;
  totalDistanceFeet: number | null;
  totalTrackedSeconds: number | null;
  mostCommonZone: WorkspaceZoneSummary | null;
  latestMatchIq: WorkspaceAnalysisRecord | null;
  recentMatches: WorkspaceAnalysisRecord[];
};

export function deriveWorkspaceSummary(records: WorkspaceAnalysisRecord[]): WorkspaceSummary {
  const recentMatches = sortRecords(records);
  const completedMatches = recentMatches.filter(isCompletedMatch);
  const distances = completedMatches
    .map((record) => record.analytics?.analytics.distance.total_distance_feet)
    .filter(isFiniteMetric);
  const trackedTimes = completedMatches
    .map((record) => record.analytics?.analytics.zone_occupancy.tracked_time_seconds)
    .filter(isFiniteMetric);

  return {
    completedMatches,
    completedMatchCount: completedMatches.length,
    completedMatchIqCount: completedMatches.filter(hasGeneratedMatchIq).length,
    totalDistanceFeet: distances.length ? sum(distances) : completedMatches.length === 0 ? 0 : null,
    totalTrackedSeconds: trackedTimes.length
      ? sum(trackedTimes)
      : completedMatches.length === 0
        ? 0
        : null,
    mostCommonZone: deriveMostCommonZone(completedMatches),
    latestMatchIq: completedMatches.find(hasGeneratedMatchIq) ?? null,
    recentMatches,
  };
}

export function isCompletedMatch(record: WorkspaceAnalysisRecord): boolean {
  return (
    record.job?.status === "completed" &&
    record.job.analytics_completed &&
    record.analytics?.analytics !== undefined
  );
}

export function hasGeneratedMatchIq(record: WorkspaceAnalysisRecord): boolean {
  return record.analytics?.match_iq?.status === "generated";
}

export function getMatchIqAvailability(record: WorkspaceAnalysisRecord): string {
  const matchIQ = record.analytics?.match_iq;
  if (matchIQ?.quality_gate === "NORMAL") {
    return "Verified movement insight";
  }
  if (matchIQ?.quality_gate === "CAUTIOUS") {
    return "Analysis under review";
  }
  if (
    matchIQ?.quality_gate === "MEASUREMENT_ONLY" ||
    matchIQ?.quality_gate === "INSUFFICIENT_EVIDENCE"
  ) {
    return "Limited by video quality";
  }
  if (record.job?.status === "failed") {
    return "No verified insight yet";
  }
  if (record.job?.analytics_completed || record.analytics) {
    return "No verified insight yet";
  }
  return "Analysis under review";
}

export function getDominantZone(record: WorkspaceAnalysisRecord): WorkspaceZoneSummary | null {
  const zones = record.analytics?.analytics.zone_occupancy;
  if (!zones) {
    return null;
  }
  const candidates: WorkspaceZoneSummary[] = [
    {
      key: "kitchen",
      label: "Kitchen",
      percentage: zones.kitchen.percentage,
      seconds: zones.kitchen.seconds,
    },
    {
      key: "transition",
      label: "Transition",
      percentage: zones.transition_zone.percentage,
      seconds: zones.transition_zone.seconds,
    },
    {
      key: "baseline",
      label: "Baseline",
      percentage: zones.baseline_area.percentage,
      seconds: zones.baseline_area.seconds,
    },
  ];
  const validCandidates = candidates.filter((zone) => isFiniteMetric(zone.percentage));

  if (validCandidates.length === 0) {
    return null;
  }
  return validCandidates.sort((first, second) => {
    if (second.percentage !== first.percentage) {
      return second.percentage - first.percentage;
    }
    return first.label.localeCompare(second.label);
  })[0];
}

export function getHumanMatchStatus(job: AnalysisJob): string {
  if (job.status === "failed") {
    return "Needs attention";
  }
  if (job.analytics_completed) {
    return "Match IQ ready";
  }
  if (job.player_selected) {
    return "Ready for Match IQ";
  }
  if (job.tracking_completed) {
    return "Select yourself";
  }
  if (job.calibration_completed) {
    return "Finding players";
  }
  if (job.inspection_completed) {
    return "Court recognition";
  }
  return "Uploading";
}

export function sortRecords(records: WorkspaceAnalysisRecord[]): WorkspaceAnalysisRecord[] {
  return [...records].sort((first, second) => {
    const secondTime = recordTimestamp(second);
    const firstTime = recordTimestamp(first);
    if (secondTime !== firstTime) {
      return secondTime - firstTime;
    }
    return first.analysisId.localeCompare(second.analysisId);
  });
}

export function formatDistanceFeet(value: number | null): string {
  if (!isFiniteMetric(value)) {
    return "Unavailable";
  }
  return `${value.toFixed(1)} ft`;
}

export function formatTrackedTime(value: number | null): string {
  if (!isFiniteMetric(value)) {
    return "Unavailable";
  }
  if (value < 60) {
    return `${value.toFixed(1)} sec`;
  }
  return `${(value / 60).toFixed(1)} min`;
}

function deriveMostCommonZone(
  records: WorkspaceAnalysisRecord[],
): WorkspaceZoneSummary | null {
  const totals: Record<WorkspaceZoneSummary["key"], WorkspaceZoneSummary> = {
    kitchen: { key: "kitchen", label: "Kitchen", percentage: 0, seconds: 0 },
    transition: { key: "transition", label: "Transition", percentage: 0, seconds: 0 },
    baseline: { key: "baseline", label: "Baseline", percentage: 0, seconds: 0 },
  };

  for (const record of records) {
    const zones = record.analytics?.analytics.zone_occupancy;
    if (!zones) {
      continue;
    }
    if (isFiniteMetric(zones.kitchen.seconds)) {
      totals.kitchen.seconds = (totals.kitchen.seconds ?? 0) + zones.kitchen.seconds;
    }
    if (isFiniteMetric(zones.transition_zone.seconds)) {
      totals.transition.seconds = (totals.transition.seconds ?? 0) + zones.transition_zone.seconds;
    }
    if (isFiniteMetric(zones.baseline_area.seconds)) {
      totals.baseline.seconds = (totals.baseline.seconds ?? 0) + zones.baseline_area.seconds;
    }
  }

  const ordered = Object.values(totals).sort((first, second) => {
    const secondSeconds = second.seconds ?? 0;
    const firstSeconds = first.seconds ?? 0;
    if (secondSeconds !== firstSeconds) {
      return secondSeconds - firstSeconds;
    }
    return first.label.localeCompare(second.label);
  });
  const top = ordered[0];
  if (!top || !top.seconds || top.seconds <= 0) {
    return null;
  }
  return top;
}

function recordTimestamp(record: WorkspaceAnalysisRecord): number {
  const value =
    record.analytics?.analytics.created_at ?? record.job?.updated_at ?? record.job?.created_at;
  if (!value) {
    return 0;
  }
  const timestamp = new Date(value).getTime();
  return Number.isFinite(timestamp) ? timestamp : 0;
}

function isFiniteMetric(value: number | null | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0;
}

function sum(values: number[]): number {
  return values.reduce((total, value) => total + value, 0);
}
