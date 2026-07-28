import { screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AnalyticsDetails } from "@/components/analytics-details";
import { getAnalysis, getAnalytics } from "@/lib/api/analyses";
import type { MatchIQReport } from "@/lib/api/types";
import {
  makeAnalyticsReport,
  makeJob,
  makeMatchIQReport,
  makeRecordingQuality,
} from "@/test/factories";
import { renderWithQueryClient } from "@/test/render";

vi.mock("@/lib/api/analyses", () => ({
  getAnalysis: vi.fn(),
  getAnalytics: vi.fn(),
}));

vi.mock("@/lib/share-card-renderer", () => ({
  renderShareCardToCanvas: vi.fn(async () => undefined),
  createShareCardPng: vi.fn(async () => new Blob(["png"], { type: "image/png" })),
}));

const mockedGetAnalysis = vi.mocked(getAnalysis);
const mockedGetAnalytics = vi.mocked(getAnalytics);

describe("analytics details evidence narrative", () => {
  beforeEach(() => {
    mockedGetAnalytics.mockReset();
    mockedGetAnalysis.mockReset();
    mockedGetAnalysis.mockResolvedValue(makeJob());
  });

  it("renders the evidence-to-insight hierarchy with unchanged measurements", async () => {
    mockedGetAnalytics.mockResolvedValue({
      analysis_id: "analysis-123",
      analytics: makeAnalyticsReport(),
      match_iq: makeMatchIQReport({
        quality_gate: "NORMAL",
        confidence: confidenceFixture(),
      }),
    });

    renderWithQueryClient(<AnalyticsDetails analysisId="analysis-123" />);

    expect(await screen.findByRole("heading", { name: "Video Quality" })).toBeInTheDocument();
    const headingNames = screen
      .getAllByRole("heading", { level: 2 })
      .map((heading) => heading.textContent);
    expect(headingNames.indexOf("Observation Coverage")).toBeLessThan(
      headingNames.indexOf("Movement Measurements"),
    );
    expect(headingNames.indexOf("Movement Measurements")).toBeLessThan(
      headingNames.indexOf("Evidence Confidence"),
    );
    expect(headingNames.indexOf("Evidence Confidence")).toBeLessThan(
      headingNames.indexOf("Movement Insight"),
    );
    expect(headingNames.indexOf("Movement Insight")).toBeLessThan(
      headingNames.indexOf("Observed Court Position"),
    );
    expect(headingNames.indexOf("Observed Court Position")).toBeLessThan(
      headingNames.indexOf("Movement Maps"),
    );
    expect(headingNames.indexOf("Movement Maps")).toBeLessThan(
      headingNames.indexOf("Limitations and Video Guidance"),
    );

    expect(screen.getAllByText("42.5 ft").length).toBeGreaterThan(0);
    expect(screen.getByText("13.0 m")).toBeInTheDocument();
    expect(screen.getByText("2.50 ft/s")).toBeInTheDocument();
    expect(screen.getByText("10.0 ft, 12.0 ft")).toBeInTheDocument();
    expect(screen.getAllByText("40.0%").length).toBe(2);
    expect(screen.getByText("20.0%")).toBeInTheDocument();
    expect(screen.getByText("Transition-zone time was the largest positioning signal")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Share Performance Card" })).toBeInTheDocument();
  });

  it("shows valid observation coverage from persisted durations", async () => {
    mockedGetAnalysis.mockResolvedValue(
      makeJob({
        upload_preflight: makeRecordingQuality({
          stage: "UPLOAD_PREFLIGHT",
          upload_signals: {
            format: ".mp4",
            orientation: "landscape",
            width: 1920,
            height: 1080,
            fps: 30,
            duration_seconds: 392,
          },
          analysis_signals: null,
        }),
      }),
    );
    mockedGetAnalytics.mockResolvedValue({
      analysis_id: "analysis-123",
      analytics: makeAnalyticsReport({ observed_duration_seconds: 298 }),
      match_iq: makeMatchIQReport({ confidence: confidenceFixture() }),
    });

    renderWithQueryClient(<AnalyticsDetails analysisId="analysis-123" />);

    const coverage = await screen.findByRole("heading", { name: "Observation Coverage" });
    const section = coverage.closest("section");
    expect(section).not.toBeNull();
    expect(within(section!).getByText("Court4 reliably observed 76% of this video.")).toBeInTheDocument();
    expect(within(section!).getByText("6m 32s")).toBeInTheDocument();
    expect(within(section!).getByText("4m 58s")).toBeInTheDocument();
    expect(within(section!).getByText("1m 34s")).toBeInTheDocument();
    expect(within(section!).getByText("Moderate")).toBeInTheDocument();
    expect(within(section!).getByRole("progressbar")).toHaveAttribute("value", expect.stringMatching(/^76/));
  });

  it("does not turn unavailable or legacy coverage into zero percent", async () => {
    mockedGetAnalytics.mockResolvedValueOnce({
      analysis_id: "analysis-123",
      analytics: makeAnalyticsReport({ observed_duration_seconds: 0 }),
      match_iq: makeMatchIQReport(),
    });
    const first = renderWithQueryClient(<AnalyticsDetails analysisId="analysis-123" />);

    expect(await screen.findByText("Not available")).toBeInTheDocument();
    expect(screen.getByText("Not enough reliable tracking was available to calculate coverage.")).toBeInTheDocument();
    expect(screen.queryByText("0%")).not.toBeInTheDocument();

    first.unmount();
    mockedGetAnalytics.mockResolvedValueOnce({
      analysis_id: "analysis-123",
      analytics: makeAnalyticsReport({ observed_duration_seconds: undefined }),
      match_iq: null,
    });
    renderWithQueryClient(<AnalyticsDetails analysisId="analysis-123" />);

    expect(await screen.findByText("Legacy analysis — coverage unavailable")).toBeInTheDocument();
    expect(screen.queryByText("0%")).not.toBeInTheDocument();
  });

  it("connects all five confidence stages with accessible status labels", async () => {
    mockedGetAnalytics.mockResolvedValue({
      analysis_id: "analysis-123",
      analytics: makeAnalyticsReport(),
      match_iq: makeMatchIQReport({ confidence: confidenceFixture() }),
    });

    renderWithQueryClient(<AnalyticsDetails analysisId="analysis-123" />);

    const chain = await screen.findByRole("list", {
      name: "Evidence confidence dependency chain",
    });
    expect(within(chain).getByText("Video")).toBeInTheDocument();
    expect(within(chain).getByText("Tracking")).toBeInTheDocument();
    expect(within(chain).getByText("Measurement")).toBeInTheDocument();
    expect(within(chain).getByText("Interpretation")).toBeInTheDocument();
    expect(within(chain).getByText("Recommendation")).toBeInTheDocument();
    expect(within(chain).getAllByText("High")).toHaveLength(1);
    expect(within(chain).getAllByText("Moderate")).toHaveLength(2);
    expect(within(chain).getAllByText("Low")).toHaveLength(1);
    expect(within(chain).getAllByText("Unavailable")).toHaveLength(1);
    expect(within(chain).getAllByRole("listitem")).toHaveLength(5);
  });

  it("explains unsuitable evidence and recovery without internal codes", async () => {
    const unsuitable = makeRecordingQuality({
      status: "UNSUITABLE",
      passed_checks: [],
      warnings: [],
      blocking_failures: [
        {
          code: "upload_preflight_blocked",
          label: "Upload preflight",
          status: "FAILED",
          message: "The upload preflight contains a blocking recording failure.",
          measured_value: null,
        },
        {
          code: "tracking_gaps_excessive",
          label: "Tracking gaps",
          status: "FAILED",
          message: "Unobserved gaps exceed half of the selected candidate span.",
          measured_value: "72%",
        },
      ],
      reason_codes: ["upload_preflight_blocked", "tracking_gaps_excessive"],
      guidance: [
        "Capture a longer continuous section of gameplay.",
        "Keep the full court visible and the camera stable.",
      ],
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
        confidence: confidenceFixture(),
        recording_quality: unsuitable,
      }),
    });

    renderWithQueryClient(<AnalyticsDetails analysisId="analysis-123" />);

    expect(await screen.findByText("This video isn’t suitable for reliable match analysis.")).toBeInTheDocument();
    expect(screen.getByText("The video did not meet the minimum quality requirements.")).toBeInTheDocument();
    expect(screen.getByText("Player tracking was too fragmented for a trustworthy insight.")).toBeInTheDocument();
    expect(screen.getByText("Record a longer continuous section of gameplay.")).toBeInTheDocument();
    expect(screen.getByText("Keep the full court visible and the camera stable.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Why no Match IQ is shown" })).toBeInTheDocument();
    expect(screen.getByText(/not reliable enough to generate a trustworthy movement insight/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Try another video" })).toHaveAttribute(
      "href",
      "/upload-match",
    );
    expect(screen.queryByText("upload_preflight_blocked")).not.toBeInTheDocument();
    expect(screen.queryByText("tracking_gaps_excessive")).not.toBeInTheDocument();
    expect(screen.queryByText(/upload preflight contains/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Share Performance Card" })).not.toBeInTheDocument();
  });

  it("labels measurement-only output without presenting suppression as an error", async () => {
    const report = makeMatchIQReport({
      quality_gate: "MEASUREMENT_ONLY",
      summary:
        "Court4 measured movement, but recording or tracking limitations remain.",
      focus: null,
      confidence: confidenceFixture(),
    });
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

    expect(
      (await screen.findAllByText("Measurement only", { exact: true })).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText("Court4 is keeping this as a measurement because the evidence is limited.").length,
    ).toBeGreaterThan(0);
    expect(
      screen.getByText("Court4 measured movement, but video or tracking limitations remain."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/\brecording\b/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/suppressed/i)).not.toBeInTheDocument();
  });

  it("clarifies position, maps, markers, and grouped limitations", async () => {
    mockedGetAnalytics.mockResolvedValue({
      analysis_id: "analysis-123",
      analytics: makeAnalyticsReport({
        source_fragment_count: 2,
        unobserved_gap_seconds: 4,
        continuity_warnings: [
          "movement_combines_multiple_track_fragments",
          "unobserved_gaps_not_interpolated",
        ],
      }),
      match_iq: makeMatchIQReport({ confidence: confidenceFixture() }),
    });

    renderWithQueryClient(<AnalyticsDetails analysisId="analysis-123" />);

    expect(await screen.findByRole("heading", { name: "Observed Court Position" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Zone occupancy" })).not.toBeInTheDocument();
    expect(screen.getByText(/describe where Court4 observed you during the reliably tracked sample/i)).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Observed movement heatmap" })).toBeInTheDocument();
    expect(screen.getByText("Measurement only", { exact: true })).toBeInTheDocument();
    expect(screen.getByText(/Warmer areas were observed more often/i)).toBeInTheDocument();
    expect(screen.getByText("Tracking started here")).toBeInTheDocument();
    expect(screen.getByText("Tracking ended here")).toBeInTheDocument();
    expect(screen.getByText(/line follows Court4's estimated player position/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Video limitations" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Tracking limitations" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Analysis limitations" })).toBeInTheDocument();
    expect(screen.getByText(/did not evaluate shots, serves, rallies/i)).toBeInTheDocument();
    expect(screen.getByText(/geometry, not whether positioning was good or bad/i)).toBeInTheDocument();
    expect(screen.queryByText("movement_combines_multiple_track_fragments")).not.toBeInTheDocument();
  });

  it("keeps Active Play and internal identifiers off the player page", async () => {
    mockedGetAnalytics.mockResolvedValue({
      analysis_id: "analysis-123",
      analytics: makeAnalyticsReport(),
      match_iq: makeMatchIQReport({ confidence: confidenceFixture() }),
    });

    renderWithQueryClient(<AnalyticsDetails analysisId="analysis-123" />);

    await screen.findByRole("heading", { name: "Movement Insight" });
    expect(screen.queryByText(/LIKELY_ACTIVE|LIKELY_IDLE|active-play-v1/i)).not.toBeInTheDocument();
    expect(screen.queryByText("positioning-high-transition-v1")).not.toBeInTheDocument();
    expect(screen.queryByText("auto-court-detection")).not.toBeInTheDocument();
    expect(screen.queryByText("Selected track ID")).not.toBeInTheDocument();
  });
});

function confidenceFixture(): NonNullable<MatchIQReport["confidence"]> {
  return {
    recording: { level: "HIGH", rationale: "Persisted recording rationale." },
    tracking: { level: "MODERATE", rationale: "Persisted tracking rationale." },
    measurement: { level: "MODERATE", rationale: "Persisted measurement rationale." },
    interpretation: { level: "LOW", rationale: "Persisted interpretation rationale." },
    recommendation: { level: "NOT_AVAILABLE", rationale: "Persisted recommendation rationale." },
  };
}
