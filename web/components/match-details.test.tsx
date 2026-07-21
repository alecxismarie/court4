import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MatchDetails } from "@/components/match-details";
import { Court4ApiError } from "@/lib/api/client";
import {
  detectCourt,
  generateAnalytics,
  getAnalysis,
  getAnalysisFrames,
  getPlayers,
  selectPlayer,
  startTracking,
} from "@/lib/api/analyses";
import {
  makeAnalyticsGenerationResponse,
  makeArtifact,
  makeCourtDetectionResponse,
  makeFrame,
  makeJob,
  makePlayerSelectionResponse,
  makePlayersResponse,
  makeTrackingResponse,
} from "@/test/factories";
import { renderWithQueryClient } from "@/test/render";

const pushMock = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

vi.mock("@/lib/api/analyses", () => ({
  detectCourt: vi.fn(),
  generateAnalytics: vi.fn(),
  getAnalysis: vi.fn(),
  getAnalysisFrames: vi.fn(),
  getPlayers: vi.fn(),
  selectPlayer: vi.fn(),
  startTracking: vi.fn(),
}));

const mockedDetectCourt = vi.mocked(detectCourt);
const mockedGenerateAnalytics = vi.mocked(generateAnalytics);
const mockedGetAnalysis = vi.mocked(getAnalysis);
const mockedGetAnalysisFrames = vi.mocked(getAnalysisFrames);
const mockedGetPlayers = vi.mocked(getPlayers);
const mockedSelectPlayer = vi.mocked(selectPlayer);
const mockedStartTracking = vi.mocked(startTracking);

describe("match details workflow", () => {
  beforeEach(() => {
    pushMock.mockClear();
    mockedDetectCourt.mockReset();
    mockedGenerateAnalytics.mockReset();
    mockedGetAnalysis.mockReset();
    mockedGetAnalysisFrames.mockReset();
    mockedGetPlayers.mockReset();
    mockedSelectPlayer.mockReset();
    mockedStartTracking.mockReset();
  });

  it("shows a loading state while the analysis is loading", () => {
    mockedGetAnalysis.mockReturnValue(new Promise(() => {}));

    renderWithQueryClient(<MatchDetails analysisId="analysis-123" />);

    expect(
      screen.getByRole("status", { name: "Loading match details" }),
    ).toBeInTheDocument();
  });

  it("shows normalized API errors when loading fails", async () => {
    mockedGetAnalysis.mockRejectedValue(
      new Court4ApiError("Analysis does not exist.", {
        code: "analysis_not_found",
        status: 404,
      }),
    );

    renderWithQueryClient(<MatchDetails analysisId="missing-analysis" />);

    expect(await screen.findByText("Match could not be loaded")).toBeInTheDocument();
    expect(screen.getByText("Analysis does not exist.")).toBeInTheDocument();
    expect(mockedGetAnalysisFrames).not.toHaveBeenCalled();
  });

  it("loads sampled frames and offers automatic court detection after inspection", async () => {
    mockedGetAnalysis.mockResolvedValue(makeJob({ analysis_id: "analysis-123" }));
    mockedGetAnalysisFrames.mockResolvedValue({
      analysis_id: "analysis-123",
      frames: [makeFrame()],
    });

    renderWithQueryClient(<MatchDetails analysisId="analysis-123" />);

    expect(await screen.findByText("Detect the court")).toBeInTheDocument();
    expect(await screen.findByText("frame_000001.jpg")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /detect court/i })).toBeInTheDocument();
  });

  it("shows detection success artifacts and exposes player tracking", async () => {
    const user = userEvent.setup();
    const calibratedJob = makeJob({
      current_stage: "calibrated",
      calibration_completed: true,
      available_artifacts: [
        makeArtifact({
          path: "calibrations/auto-court-detection/calibration.json",
          content_type: "application/json",
        }),
        makeArtifact(),
        makeArtifact({
          path: "calibrations/auto-court-detection/top_down.jpg",
        }),
      ],
    });
    mockedGetAnalysis.mockResolvedValueOnce(makeJob()).mockResolvedValue(calibratedJob);
    mockedGetAnalysisFrames.mockResolvedValue({ analysis_id: "analysis-123", frames: [] });
    mockedDetectCourt.mockResolvedValue(makeCourtDetectionResponse());

    renderWithQueryClient(<MatchDetails analysisId="analysis-123" />);
    await user.click(await screen.findByRole("button", { name: /detect court/i }));

    expect(await screen.findByText("Court detected with 91% confidence.")).toBeInTheDocument();
    expect(await screen.findByText("Start player tracking")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Verification" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Top-down" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /start player tracking/i })).toBeInTheDocument();
  });

  it("shows manual calibration fallback when detection is low confidence", async () => {
    const user = userEvent.setup();
    mockedGetAnalysis
      .mockResolvedValueOnce(makeJob())
      .mockResolvedValue(
        makeJob({
          manual_calibration_required: true,
        }),
      );
    mockedGetAnalysisFrames.mockResolvedValue({ analysis_id: "analysis-123", frames: [] });
    mockedDetectCourt.mockResolvedValue(
      makeCourtDetectionResponse({
        status: "low_confidence",
        confidence: 0.42,
        calibration: null,
        artifacts: [],
        manual_calibration_required: true,
      }),
    );

    renderWithQueryClient(<MatchDetails analysisId="analysis-123" />);
    await user.click(await screen.findByRole("button", { name: /detect court/i }));

    expect(
      await screen.findByText("Court4 could not confidently detect the court."),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /calibrate manually/i })).toBeInTheDocument();
  });

  it("starts tracking and displays eligible player tracks", async () => {
    const user = userEvent.setup();
    mockedGetAnalysis
      .mockResolvedValueOnce(makeCalibratedJob())
      .mockResolvedValue(makeJob({ ...makeCalibratedFlags(), tracking_completed: true }));
    mockedGetAnalysisFrames.mockResolvedValue({ analysis_id: "analysis-123", frames: [] });
    mockedStartTracking.mockResolvedValue(makeTrackingResponse());
    mockedGetPlayers.mockResolvedValue(makePlayersResponse());

    renderWithQueryClient(<MatchDetails analysisId="analysis-123" />);
    await user.selectOptions(await screen.findByLabelText("Backend"), "controlled-json");
    await user.click(screen.getByRole("button", { name: /start player tracking/i }));

    await waitFor(() =>
      expect(mockedStartTracking).toHaveBeenCalledWith("analysis-123", {
        calibration_id: "auto-court-detection",
        backend: "controlled-json",
        detections_jsonl: "uploads/detections.jsonl",
        frame_interval: 1,
      }),
    );
    expect(await screen.findByText("Track 1")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /this is me/i })).toBeInTheDocument();
  });

  it("selects an eligible player track and generates analytics", async () => {
    const user = userEvent.setup();
    mockedGetAnalysis
      .mockResolvedValueOnce(makeJob({ ...makeCalibratedFlags(), tracking_completed: true }))
      .mockResolvedValue(
        makeJob({
          ...makeCalibratedFlags(),
          tracking_completed: true,
          player_selected: true,
        }),
      );
    mockedGetAnalysisFrames.mockResolvedValue({ analysis_id: "analysis-123", frames: [] });
    mockedGetPlayers.mockResolvedValue(makePlayersResponse());
    mockedSelectPlayer.mockResolvedValue(makePlayerSelectionResponse());
    mockedGenerateAnalytics.mockResolvedValue(makeAnalyticsGenerationResponse());

    renderWithQueryClient(<MatchDetails analysisId="analysis-123" />);
    await user.click(await screen.findByRole("button", { name: /this is me/i }));

    await waitFor(() => expect(mockedSelectPlayer).toHaveBeenCalledWith("analysis-123", 1));
    await user.click(await screen.findByRole("button", { name: /generate my analytics/i }));

    await waitFor(() => expect(mockedGenerateAnalytics).toHaveBeenCalledWith("analysis-123"));
    expect(pushMock).toHaveBeenCalledWith("/matches/analysis-123/analytics");
  });
});

function makeCalibratedFlags() {
  return {
    current_stage: "calibrated",
    calibration_completed: true,
    available_artifacts: [
      makeArtifact({
        path: "calibrations/auto-court-detection/calibration.json",
        content_type: "application/json",
      }),
      makeArtifact(),
    ],
  };
}

function makeCalibratedJob() {
  return makeJob(makeCalibratedFlags());
}
