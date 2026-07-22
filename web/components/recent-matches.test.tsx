import { screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { RecentMatches } from "@/components/recent-matches";
import type { AnalyticsResponse } from "@/lib/api/types";
import { deriveWorkspaceSummary, type WorkspaceAnalysisRecord } from "@/lib/workspace-data";
import { makeAnalyticsReport, makeJob, makeMatchIQReport } from "@/test/factories";
import { renderWithQueryClient } from "@/test/render";

const workspaceMock = vi.hoisted(() => vi.fn());

vi.mock("@/lib/use-workspace-analyses", () => ({
  useWorkspaceAnalyses: workspaceMock,
}));

describe("recent matches", () => {
  beforeEach(() => {
    workspaceMock.mockReturnValue(makeWorkspace([]));
  });

  it("shows human-readable statuses and actions only when Match IQ is available", () => {
    workspaceMock.mockReturnValue(
      makeWorkspace([
        makeCompletedRecord("complete", { matchIQ: makeMatchIQReport({ analysis_id: "complete" }) }),
        {
          analysisId: "select-me",
          job: makeJob({
            analysis_id: "select-me",
            calibration_completed: true,
            tracking_completed: true,
          }),
          analytics: null,
        },
        {
          analysisId: "failed",
          job: makeJob({ analysis_id: "failed", status: "failed", error: "tracking failed" }),
          analytics: null,
        },
      ]),
    );

    renderWithQueryClient(<RecentMatches />);

    const completedRow = rowFor("complete");
    expect(within(completedRow).getByText("Match IQ ready")).toBeInTheDocument();
    expect(within(completedRow).getByText("Match IQ available")).toBeInTheDocument();
    expect(within(completedRow).getByRole("link", { name: /^view match$/i })).toHaveAttribute(
      "href",
      "/matches/complete",
    );
    expect(within(completedRow).getByRole("link", { name: /view match iq/i })).toHaveAttribute(
      "href",
      "/matches/complete/analytics",
    );
    expect(within(completedRow).getByRole("link", { name: /^share$/i })).toHaveAttribute(
      "href",
      "/matches/complete/analytics#share-card",
    );

    const selectionRow = rowFor("select-me");
    expect(within(selectionRow).getByText("Select yourself")).toBeInTheDocument();
    expect(within(selectionRow).getByText("Match IQ pending")).toBeInTheDocument();
    expect(within(selectionRow).queryByRole("link", { name: /view match iq/i })).not.toBeInTheDocument();
    expect(within(selectionRow).queryByRole("link", { name: /^share$/i })).not.toBeInTheDocument();

    const failedRow = rowFor("failed");
    expect(within(failedRow).getByText("Needs attention")).toBeInTheDocument();
    expect(within(failedRow).getByText("Match IQ unavailable")).toBeInTheDocument();
    expect(within(failedRow).queryByRole("link", { name: /view match iq/i })).not.toBeInTheDocument();
    expect(within(failedRow).queryByRole("link", { name: /^share$/i })).not.toBeInTheDocument();
  });

  it("keeps legacy analytics available without Match IQ or share actions", () => {
    workspaceMock.mockReturnValue(makeWorkspace([makeCompletedRecord("legacy", { matchIQ: null })]));

    renderWithQueryClient(<RecentMatches />);

    const legacyRow = rowFor("legacy");
    expect(within(legacyRow).getByText("Match IQ unavailable")).toBeInTheDocument();
    expect(within(legacyRow).getByText("42.5 ft")).toBeInTheDocument();
    expect(within(legacyRow).getByText("Baseline 40.0%")).toBeInTheDocument();
    expect(within(legacyRow).queryByRole("link", { name: /view match iq/i })).not.toBeInTheDocument();
    expect(within(legacyRow).queryByRole("link", { name: /^share$/i })).not.toBeInTheDocument();
  });
});

function rowFor(text: string): HTMLElement {
  const row = screen.getByText(text).closest("article");
  expect(row).not.toBeNull();
  return row!;
}

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
  options: { matchIQ?: AnalyticsResponse["match_iq"] } = {},
): WorkspaceAnalysisRecord {
  const analytics = makeAnalyticsReport({ analysis_id: analysisId });
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
          ? makeMatchIQReport({ analysis_id: analysisId })
          : options.matchIQ,
    },
  };
}
