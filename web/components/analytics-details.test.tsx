import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AnalyticsDetails } from "@/components/analytics-details";
import { getAnalytics } from "@/lib/api/analyses";
import {
  makeAnalyticsReport,
  makeMatchIQReport,
  makeRecordingQuality,
} from "@/test/factories";
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
    mockedGetAnalytics.mockResolvedValue({
      analysis_id: "analysis-123",
      analytics: makeAnalyticsReport(),
      match_iq: makeMatchIQReport(),
    });

    renderWithQueryClient(<AnalyticsDetails analysisId="analysis-123" />);

    expect(await screen.findByText("What Court4 observed")).toBeInTheDocument();
    expect((await screen.findAllByText("42.5 ft")).length).toBeGreaterThan(0);
    expect(screen.getByText("Movement insight")).toBeInTheDocument();
    expect(screen.getByText("Transition-zone time was the largest positioning signal")).toBeInTheDocument();
    expect(screen.getAllByText("60.0%").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Observation").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Evidence").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Confidence").length).toBeGreaterThan(0);
    expect(screen.getAllByText("What it may mean").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Limitations").length).toBeGreaterThan(0);
    expect(screen.getAllByText("What to review next").length).toBeGreaterThan(0);
    expect(screen.getByText("Share Performance Card")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Download PNG/ })).toBeInTheDocument();
    expect(screen.queryByText("Personalized observations and recommendations will appear here in the next phase.")).not.toBeInTheDocument();
    expect(screen.queryByText("positioning-high-transition-v1")).not.toBeInTheDocument();
    expect(screen.queryByText("Selected track ID")).not.toBeInTheDocument();
    expect(screen.queryByText("auto-court-detection")).not.toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "How to read your movement maps" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/They show player movement, not the ball's path/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Red and yellow areas were visited most often/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/The green dot marks where tracking started/i),
    ).toBeInTheDocument();
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

    expect(
      await screen.findByText("No verified insight yet. Movement measurements remain available above."),
    ).toBeInTheDocument();
  });

  it("suppresses normal insight cards and offers retry for unsuitable evidence", async () => {
    const unsuitable = makeRecordingQuality({
      status: "UNSUITABLE",
      passed_checks: [],
      warnings: [],
      blocking_failures: [
        {
          code: "tracking_gaps_excessive",
          label: "Tracking gaps",
          status: "FAILED",
          message: "Unobserved gaps exceed half of the selected candidate span.",
          measured_value: "72%",
        },
      ],
      reason_codes: ["tracking_gaps_excessive"],
      guidance: ["Keep the full court visible and the camera stable."],
    });
    mockedGetAnalytics.mockResolvedValue({
      analysis_id: "analysis-123",
      analytics: makeAnalyticsReport(),
      match_iq: makeMatchIQReport({
        status: "insufficient_data",
        quality_gate: "INSUFFICIENT_EVIDENCE",
        summary: "Insufficient evidence for a verified movement insight.",
        insights: [],
        focus: null,
        recording_quality: unsuitable,
      }),
    });

    renderWithQueryClient(<AnalyticsDetails analysisId="analysis-123" />);

    expect(await screen.findByText("Unsuitable")).toBeInTheDocument();
    expect(screen.getByText("Normal Match IQ is suppressed")).toBeInTheDocument();
    expect(screen.queryByText("Transition-zone time was the largest positioning signal")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /try another recording/i })).toHaveAttribute(
      "href",
      "/matches/upload",
    );
    expect(screen.queryByText("Share Performance Card")).not.toBeInTheDocument();
  });

  it("renders measurement-only output without interpretation or advice", async () => {
    const report = makeMatchIQReport({ quality_gate: "MEASUREMENT_ONLY", focus: null });
    mockedGetAnalytics.mockResolvedValue({
      analysis_id: "analysis-123",
      analytics: makeAnalyticsReport(),
      match_iq: {
        ...report,
        insights: report.insights.map((insight) => ({
          ...insight,
          quality_gate: "MEASUREMENT_ONLY",
          interpretation: null,
          action: null,
        })),
      },
    });

    renderWithQueryClient(<AnalyticsDetails analysisId="analysis-123" />);

    expect(await screen.findByText("Limited by recording quality")).toBeInTheDocument();
    expect(
      screen.getAllByText("Interpretation is suppressed because the evidence is limited.").length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText("No next-step advice is shown for this evidence level.").length,
    ).toBeGreaterThan(0);
  });
});
