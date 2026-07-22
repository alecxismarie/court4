import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PerformanceWorkspace } from "@/components/performance-workspace";
import type { AnalyticsResponse } from "@/lib/api/types";
import { deriveWorkspaceSummary, type WorkspaceAnalysisRecord } from "@/lib/workspace-data";
import { makeAnalyticsReport, makeJob, makeMatchIQReport } from "@/test/factories";
import { renderWithQueryClient } from "@/test/render";

const workspaceMock = vi.hoisted(() => vi.fn());

vi.mock("@/lib/use-workspace-analyses", () => ({
  useWorkspaceAnalyses: workspaceMock,
}));

describe("performance workspace", () => {
  beforeEach(() => {
    workspaceMock.mockReturnValue(makeWorkspace([]));
  });

  it("renders a factual snapshot and future progress state without fake comparisons", () => {
    workspaceMock.mockReturnValue(
      makeWorkspace([
        makeCompletedRecord("match-a", {
          distanceFeet: 30,
          trackedSeconds: 60,
          zoneSeconds: { kitchen: 45, transition: 10, baseline: 5 },
          createdAt: "2026-07-21T00:00:00Z",
        }),
        makeCompletedRecord("match-b", {
          distanceFeet: 25,
          trackedSeconds: 30,
          zoneSeconds: { kitchen: 15, transition: 10, baseline: 5 },
          createdAt: "2026-07-22T00:00:00Z",
        }),
      ]),
    );

    renderWithQueryClient(<PerformanceWorkspace />);

    expect(screen.getByRole("heading", { name: "Current performance snapshot" })).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("55.0 ft")).toBeInTheDocument();
    expect(screen.getByText("1.5 min")).toBeInTheDocument();
    expect(screen.getByText("Kitchen 1.0 min")).toBeInTheDocument();
    expect(screen.getByText(/Progress trends will appear here/)).toBeInTheDocument();
    expect(screen.queryByText(/improvement/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/rating/i)).not.toBeInTheDocument();
  });

  it("handles partial analytics without rendering NaN or fake values", () => {
    workspaceMock.mockReturnValue(
      makeWorkspace([
        makeCompletedRecord("partial", {
          distanceFeet: Number.NaN,
          trackedSeconds: Number.POSITIVE_INFINITY,
          zoneSeconds: { kitchen: 0, transition: 0, baseline: 0 },
          matchIQ: null,
        }),
      ]),
    );

    renderWithQueryClient(<PerformanceWorkspace />);

    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getAllByText("Unavailable").length).toBeGreaterThanOrEqual(2);
    expect(screen.queryByText(/NaN/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Infinity/)).not.toBeInTheDocument();
    expect(screen.getByText("No completed Match IQ reports yet")).toBeInTheDocument();
  });
});

function makeWorkspace(records: WorkspaceAnalysisRecord[]) {
  return {
    analysisIds: records.map((record) => record.analysisId),
    records,
    summary: deriveWorkspaceSummary(records),
    isLoading: false,
    hasBackendError: false,
  };
}

function makeCompletedRecord(
  analysisId: string,
  options: {
    distanceFeet?: number;
    trackedSeconds?: number;
    zoneSeconds?: { kitchen: number; transition: number; baseline: number };
    createdAt?: string;
    matchIQ?: AnalyticsResponse["match_iq"];
  } = {},
): WorkspaceAnalysisRecord {
  const zoneSeconds = options.zoneSeconds ?? { kitchen: 1, transition: 2, baseline: 3 };
  const trackedSeconds = options.trackedSeconds ?? 6;
  const analytics = makeAnalyticsReport({
    analysis_id: analysisId,
    distance: {
      total_distance_feet: options.distanceFeet ?? 42.5,
      total_distance_meters: 13,
      average_movement_feet_per_second: 2.5,
      average_movement_meters_per_second: 0.76,
    },
    zone_occupancy: {
      kitchen: {
        seconds: zoneSeconds.kitchen,
        percentage: trackedSeconds ? (zoneSeconds.kitchen / trackedSeconds) * 100 : 0,
      },
      transition_zone: {
        seconds: zoneSeconds.transition,
        percentage: trackedSeconds ? (zoneSeconds.transition / trackedSeconds) * 100 : 0,
      },
      baseline_area: {
        seconds: zoneSeconds.baseline,
        percentage: trackedSeconds ? (zoneSeconds.baseline / trackedSeconds) * 100 : 0,
      },
      tracked_time_seconds: trackedSeconds,
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
