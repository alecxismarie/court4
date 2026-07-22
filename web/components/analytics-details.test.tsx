import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AnalyticsDetails } from "@/components/analytics-details";
import { getAnalytics } from "@/lib/api/analyses";
import { makeAnalyticsReport, makeMatchIQReport } from "@/test/factories";
import { renderWithQueryClient } from "@/test/render";

vi.mock("@/lib/api/analyses", () => ({
  getAnalytics: vi.fn(),
}));

vi.mock("@/lib/share-card-renderer", () => ({
  renderShareCardToCanvas: vi.fn(async () => undefined),
  createShareCardPng: vi.fn(async () => new Blob(["png"], { type: "image/png" })),
}));

const mockedGetAnalytics = vi.mocked(getAnalytics);

describe("analytics details", () => {
  beforeEach(() => {
    mockedGetAnalytics.mockReset();
  });

  it("renders factual metrics, Match IQ, and existing analytics images", async () => {
    const user = userEvent.setup();
    mockedGetAnalytics.mockResolvedValue({
      analysis_id: "analysis-123",
      analytics: makeAnalyticsReport(),
      match_iq: makeMatchIQReport(),
    });

    renderWithQueryClient(<AnalyticsDetails analysisId="analysis-123" />);

    expect(await screen.findByText("Your Match IQ")).toBeInTheDocument();
    expect(await screen.findByText("42.5 ft")).toBeInTheDocument();
    expect(screen.getByText("Match IQ Summary")).toBeInTheDocument();
    expect(screen.getByText("Transition-zone time was the largest positioning signal")).toBeInTheDocument();
    expect(screen.getByText("Transition Zone occupancy: 60.0%")).toBeInTheDocument();
    expect(screen.getByText("Share Performance Card")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Download PNG/ })).toBeInTheDocument();
    expect(screen.queryByText("Personalized observations and recommendations will appear here in the next phase.")).not.toBeInTheDocument();
    expect(screen.getByText("positioning-high-transition-v1")).not.toBeVisible();
    await user.click(screen.getAllByText("Why Court4 said this")[0]);
    expect(screen.getByText("positioning-high-transition-v1")).toBeVisible();
    expect(screen.getByText("Selected track ID")).not.toBeVisible();
    expect(screen.getByText("auto-court-detection")).not.toBeVisible();
    expect(screen.getByRole("img", { name: "Heatmap" })).toHaveAttribute(
      "src",
      "http://localhost:8000/api/v1/analyses/analysis-123/artifacts/analytics/heatmap.png",
    );
    expect(screen.getByRole("img", { name: "Trajectory" })).toBeInTheDocument();
  });

  it("renders the low-data Match IQ message without insight cards", async () => {
    mockedGetAnalytics.mockResolvedValue({
      analysis_id: "analysis-123",
      analytics: makeAnalyticsReport(),
      match_iq: makeMatchIQReport({
        status: "insufficient_data",
        summary: "Court4 does not have enough movement data to generate a reliable Match IQ.",
        insights: [],
        focus: null,
        limitations: ["Insufficient data: fewer than 3 timeline observations were available."],
      }),
    });

    renderWithQueryClient(<AnalyticsDetails analysisId="analysis-123" />);

    expect(
      await screen.findByText("Court4 does not have enough movement data to generate a reliable Match IQ."),
    ).toBeInTheDocument();
    expect(screen.queryByText("Why Court4 said this")).not.toBeInTheDocument();
  });

  it("renders legacy analytics when Match IQ is missing", async () => {
    mockedGetAnalytics.mockResolvedValue({
      analysis_id: "analysis-123",
      analytics: makeAnalyticsReport(),
      match_iq: null,
    });

    renderWithQueryClient(<AnalyticsDetails analysisId="analysis-123" />);

    expect(await screen.findByText("Match IQ was not generated for this analysis.")).toBeInTheDocument();
  });
});
