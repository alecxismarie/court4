import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DashboardWorkspace } from "@/components/dashboard-workspace";
import { emptyPlayerProfile } from "@/lib/player-profile";
import type { AnalyticsResponse } from "@/lib/api/types";
import { deriveWorkspaceSummary, type WorkspaceAnalysisRecord } from "@/lib/workspace-data";
import { makeAnalyticsReport, makeJob, makeMatchIQReport } from "@/test/factories";
import { renderWithQueryClient } from "@/test/render";

const workspaceMock = vi.hoisted(() => vi.fn());
const profileMock = vi.hoisted(() => vi.fn());

vi.mock("@/lib/use-workspace-analyses", () => ({
  useWorkspaceAnalyses: workspaceMock,
}));

vi.mock("@/lib/use-player-profile", () => ({
  usePlayerProfile: profileMock,
}));

describe("dashboard workspace", () => {
  beforeEach(() => {
    profileMock.mockReturnValue({
      profile: emptyPlayerProfile,
      isLoaded: true,
      save: vi.fn(),
    });
    workspaceMock.mockReturnValue(makeWorkspace([]));
  });

  it("shows a neutral welcome without a configured profile", () => {
    renderWithQueryClient(<DashboardWorkspace />);

    expect(screen.getByRole("heading", { name: "Welcome back" })).toBeInTheDocument();
    expect(screen.queryByText(/Welcome back,/)).not.toBeInTheDocument();
  });

  it("shows a personalized welcome with a saved display name", () => {
    profileMock.mockReturnValue({
      profile: { ...emptyPlayerProfile, displayName: "Ava" },
      isLoaded: true,
      save: vi.fn(),
    });

    renderWithQueryClient(<DashboardWorkspace />);

    expect(screen.getByRole("heading", { name: "Welcome back, Ava" })).toBeInTheDocument();
  });

  it("renders the latest Match IQ without inventing a score", () => {
    workspaceMock.mockReturnValue(makeWorkspace([makeCompletedRecord("analysis-123")]));

    renderWithQueryClient(<DashboardWorkspace />);

    expect(screen.getByText("Match IQ found 3 movement observations. Top signal: Court4 measured 60.0% of tracked time in the transition zone.")).toBeInTheDocument();
    expect(screen.getByText("Transition-zone time was the largest positioning signal")).toBeInTheDocument();
    expect(screen.getAllByText("42.5 ft").length).toBeGreaterThan(0);
    expect(screen.getByText("Matches analyzed")).toBeInTheDocument();
    expect(screen.getByText("Completed Match IQ reports")).toBeInTheDocument();
    expect(screen.queryByText(/score/i)).not.toBeInTheDocument();
  });

  it("handles legacy completed analytics without showing a latest Match IQ", () => {
    workspaceMock.mockReturnValue(
      makeWorkspace([makeCompletedRecord("legacy", { matchIQ: null })]),
    );

    renderWithQueryClient(<DashboardWorkspace />);

    expect(
      screen.getByText("Your latest Match IQ will appear here after you analyze a match."),
    ).toBeInTheDocument();
    expect(screen.getByText("Matches analyzed")).toBeInTheDocument();
    expect(screen.getAllByText("42.5 ft").length).toBeGreaterThan(0);
  });

  it("renders an honest no-match empty state", () => {
    renderWithQueryClient(<DashboardWorkspace />);

    expect(
      screen.getByText("Your latest Match IQ will appear here after you analyze a match."),
    ).toBeInTheDocument();
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
