import { describe, expect, it } from "vitest";

import type { AnalyticsResponse } from "@/lib/api/types";
import {
  deriveWorkspaceSummary,
  getDominantZone,
  getHumanMatchStatus,
  getMatchIqAvailability,
  type WorkspaceAnalysisRecord,
} from "@/lib/workspace-data";
import { makeAnalyticsReport, makeJob, makeMatchIQReport } from "@/test/factories";

describe("workspace data aggregation", () => {
  it("filters completed matches and aggregates only valid metrics", () => {
    const records: WorkspaceAnalysisRecord[] = [
      makeRecord("complete-a", {
        distanceFeet: 10,
        trackedSeconds: 3,
        zoneSeconds: { kitchen: 1, transition: 2, baseline: 0 },
        createdAt: "2026-07-21T00:00:00Z",
      }),
      makeRecord("complete-b", {
        distanceFeet: 5,
        trackedSeconds: 4,
        zoneSeconds: { kitchen: 4, transition: 0, baseline: 0 },
        createdAt: "2026-07-22T00:00:00Z",
      }),
      {
        analysisId: "incomplete",
        job: makeJob({ analysis_id: "incomplete", status: "processing" }),
        analytics: null,
      },
      makeRecord("invalid-distance", {
        distanceFeet: Number.NaN,
        trackedSeconds: Number.POSITIVE_INFINITY,
        zoneSeconds: { kitchen: 0, transition: 0, baseline: 0 },
        createdAt: "2026-07-20T00:00:00Z",
      }),
    ];

    const summary = deriveWorkspaceSummary(records);

    expect(summary.completedMatchCount).toBe(3);
    expect(summary.completedMatchIqCount).toBe(3);
    expect(summary.totalDistanceFeet).toBe(15);
    expect(summary.totalTrackedSeconds).toBe(7);
    expect(summary.mostCommonZone).toMatchObject({ label: "Kitchen", seconds: 5 });
    expect(summary.latestMatchIq?.analysisId).toBe("complete-b");
  });

  it("handles legacy analytics without Match IQ", () => {
    const summary = deriveWorkspaceSummary([
      makeRecord("legacy", {
        matchIQ: null,
        distanceFeet: 12,
        trackedSeconds: 6,
      }),
    ]);

    expect(summary.completedMatchCount).toBe(1);
    expect(summary.completedMatchIqCount).toBe(0);
    expect(summary.latestMatchIq).toBeNull();
  });

  it("sorts recent matches deterministically", () => {
    const summary = deriveWorkspaceSummary([
      makeRecord("b-record", { createdAt: "2026-07-22T00:00:00Z" }),
      makeRecord("a-record", { createdAt: "2026-07-22T00:00:00Z" }),
    ]);

    expect(summary.recentMatches.map((record) => record.analysisId)).toEqual([
      "a-record",
      "b-record",
    ]);
  });

  it("derives dominant zone and human-readable status", () => {
    const record = makeRecord("zones", {
      zonePercentages: { kitchen: 10, transition: 65, baseline: 25 },
    });

    expect(getDominantZone(record)).toMatchObject({
      label: "Transition",
      percentage: 65,
    });
    expect(getHumanMatchStatus(record.job!)).toBe("Match IQ ready");
    expect(
      getHumanMatchStatus(makeJob({ status: "failed", error: "tracking failed" })),
    ).toBe("Needs attention");
    expect(getMatchIqAvailability(record)).toBe("Match IQ available");
    expect(
      getMatchIqAvailability(makeRecord("legacy", { matchIQ: null })),
    ).toBe("Match IQ unavailable");
    expect(
      getMatchIqAvailability({
        analysisId: "pending",
        job: makeJob({ analysis_id: "pending", tracking_completed: true }),
        analytics: null,
      }),
    ).toBe("Match IQ pending");
  });
});

function makeRecord(
  analysisId: string,
  options: {
    matchIQ?: AnalyticsResponse["match_iq"];
    distanceFeet?: number;
    trackedSeconds?: number;
    zoneSeconds?: { kitchen: number; transition: number; baseline: number };
    zonePercentages?: { kitchen: number; transition: number; baseline: number };
    createdAt?: string;
  } = {},
): WorkspaceAnalysisRecord {
  const zoneSeconds = options.zoneSeconds ?? { kitchen: 1, transition: 2, baseline: 3 };
  const zonePercentages = options.zonePercentages ?? {
    kitchen: 20,
    transition: 40,
    baseline: 40,
  };
  const analytics = makeAnalyticsReport({
    analysis_id: analysisId,
    distance: {
      total_distance_feet: options.distanceFeet ?? 42.5,
      total_distance_meters: 13,
      average_movement_feet_per_second: 2.5,
      average_movement_meters_per_second: 0.76,
    },
    zone_occupancy: {
      kitchen: { seconds: zoneSeconds.kitchen, percentage: zonePercentages.kitchen },
      transition_zone: {
        seconds: zoneSeconds.transition,
        percentage: zonePercentages.transition,
      },
      baseline_area: { seconds: zoneSeconds.baseline, percentage: zonePercentages.baseline },
      tracked_time_seconds: options.trackedSeconds ?? 6,
    },
    created_at: options.createdAt ?? "2026-07-21T00:00:00Z",
  });
  return {
    analysisId,
    job: makeJob({
      analysis_id: analysisId,
      status: "completed",
      current_stage: "analyzed",
      analytics_completed: true,
      created_at: analytics.created_at,
      updated_at: analytics.created_at,
    }),
    analytics: {
      analysis_id: analysisId,
      analytics,
      match_iq:
        options.matchIQ === undefined
          ? makeMatchIQReport({ analysis_id: analysisId, created_at: analytics.created_at })
          : options.matchIQ,
    },
  };
}
