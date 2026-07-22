import { screen, waitFor, within } from "@testing-library/react";
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
  makeTrackSummary,
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
    expect(screen.getAllByText("Analysis does not exist.")[0]).toBeVisible();
    expect(mockedGetAnalysisFrames).not.toHaveBeenCalled();
  });

  it("shows backend unavailable guidance and retries loading", async () => {
    const user = userEvent.setup();
    mockedGetAnalysis
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValue(makeJob({ analysis_id: "analysis-123" }));
    mockedGetAnalysisFrames.mockResolvedValue({
      analysis_id: "analysis-123",
      frames: [],
    });

    renderWithQueryClient(<MatchDetails analysisId="analysis-123" />);

    expect(
      await screen.findByText("Court4 cannot connect to the analysis service"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Make sure the Court4 backend is running, then try again."),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /try again/i }));

    expect(await screen.findByText("Recognize the court")).toBeInTheDocument();
    expect(mockedGetAnalysis).toHaveBeenCalledTimes(2);
  });

  it("loads sampled frames and offers court recognition after inspection", async () => {
    mockedGetAnalysis.mockResolvedValue(makeJob({ analysis_id: "analysis-123" }));
    mockedGetAnalysisFrames.mockResolvedValue({
      analysis_id: "analysis-123",
      frames: [makeFrame()],
    });

    renderWithQueryClient(<MatchDetails analysisId="analysis-123" />);

    expect(await screen.findByText("Recognize the court")).toBeInTheDocument();
    expect(await screen.findByText("frame_000001.jpg")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /recognize court/i })).toBeInTheDocument();
  });

  it("shows court recognition result artifacts with technical details closed", async () => {
    const user = userEvent.setup();
    const calibratedJob = makeCalibratedJob({
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
    await user.click(await screen.findByRole("button", { name: /recognize court/i }));

    expect(await screen.findByText("Court recognized with 91% confidence.")).toBeInTheDocument();
    expect(await screen.findByText("Find the players")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Detected court" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Top-down court view" })).toBeInTheDocument();
    expect(screen.getByText("Confidence value")).not.toBeVisible();
    for (const calibrationSourceLabel of screen.getAllByText("Calibration source")) {
      expect(calibrationSourceLabel).not.toBeVisible();
    }
  });

  it("renders persisted court confidence after refresh without the original detection response", async () => {
    mockedGetAnalysis.mockResolvedValue(
      makeCalibratedJob({
        court_detection_status: "detected",
        court_detection_confidence: 0.91,
        court_detection_selected_frame: "frames/frame_000001.jpg",
        court_detection_detected_corners: makeDetectedCorners(),
        available_artifacts: [
          makeArtifact({
            path: "calibrations/auto-court-detection/calibration.json",
            content_type: "application/json",
          }),
          makeArtifact(),
        ],
      }),
    );
    mockedGetAnalysisFrames.mockResolvedValue({ analysis_id: "analysis-123", frames: [] });

    renderWithQueryClient(<MatchDetails analysisId="analysis-123" />);

    expect(await screen.findByText("Court recognized with 91% confidence.")).toBeInTheDocument();
    expect(screen.getByText("Detection confidence")).toBeInTheDocument();
    expect(screen.getAllByText("91%")[0]).toBeInTheDocument();
    expect(mockedDetectCourt).not.toHaveBeenCalled();
  });

  it("renders legacy calibrated analyses without fabricating confidence", async () => {
    mockedGetAnalysis.mockResolvedValue(makeCalibratedJob());
    mockedGetAnalysisFrames.mockResolvedValue({ analysis_id: "analysis-123", frames: [] });

    renderWithQueryClient(<MatchDetails analysisId="analysis-123" />);

    expect(await screen.findAllByText("Court recognized")).not.toHaveLength(0);
    expect(screen.queryByText("Detection confidence")).not.toBeInTheDocument();
    expect(screen.queryByText(/Court recognized with .* confidence/i)).not.toBeInTheDocument();
  });

  it("renders persisted manual calibration requirement after refresh", async () => {
    mockedGetAnalysis.mockResolvedValue(
      makeJob({
        manual_calibration_required: true,
        court_detection_status: "low_confidence",
        court_detection_confidence: 0.42,
        court_detection_selected_frame: "frames/frame_000001.jpg",
        court_detection_detected_corners: makeDetectedCorners(),
      }),
    );
    mockedGetAnalysisFrames.mockResolvedValue({ analysis_id: "analysis-123", frames: [] });

    renderWithQueryClient(<MatchDetails analysisId="analysis-123" />);

    expect(
      await screen.findByText("Court4 could not confidently recognize the court."),
    ).toBeInTheDocument();
    expect(screen.getByText("Confidence was 42%. Manual calibration is required.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /calibrate manually/i })).toBeInTheDocument();
    expect(mockedDetectCourt).not.toHaveBeenCalled();
  });

  it("shows manual calibration fallback when court confidence is low", async () => {
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
    await user.click(await screen.findByRole("button", { name: /recognize court/i }));

    expect(
      await screen.findAllByText("Court4 could not confidently recognize the court."),
    ).toHaveLength(1);
    expect(screen.getByText("Confidence was 42%. Manual calibration is required.")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /calibrate manually/i })).toHaveLength(1);
  });

  it("keeps tracking options hidden in advanced settings by default", async () => {
    mockedGetAnalysis.mockResolvedValue(makeCalibratedJob());
    mockedGetAnalysisFrames.mockResolvedValue({ analysis_id: "analysis-123", frames: [] });

    renderWithQueryClient(<MatchDetails analysisId="analysis-123" />);

    expect(await screen.findByText("Find the players")).toBeInTheDocument();
    expect(screen.getByText("Advanced settings")).toBeVisible();
    expect(screen.getByText("Detector backend")).not.toBeVisible();
    expect(screen.getByText("Frame interval")).not.toBeVisible();
    expect(screen.getByRole("button", { name: /find players/i })).toBeInTheDocument();
  });

  it("shows the player-tracking loading state and prevents duplicate requests", async () => {
    const user = userEvent.setup();
    mockedGetAnalysis.mockResolvedValue(makeCalibratedJob());
    mockedGetAnalysisFrames.mockResolvedValue({ analysis_id: "analysis-123", frames: [] });
    mockedStartTracking.mockReturnValue(new Promise(() => {}));

    renderWithQueryClient(<MatchDetails analysisId="analysis-123" />);
    await user.click(await screen.findByRole("button", { name: /find players/i }));
    await user.click(screen.getByRole("button", { name: /finding players/i }));

    expect(mockedStartTracking).toHaveBeenCalledTimes(1);
    expect(screen.getByText("Tracking player movement now.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /finding players/i })).toBeDisabled();
  });

  it("starts tracking with existing default request values and displays eligible player cards", async () => {
    const user = userEvent.setup();
    mockedGetAnalysis
      .mockResolvedValueOnce(makeCalibratedJob())
      .mockResolvedValue(makeTrackedJob());
    mockedGetAnalysisFrames.mockResolvedValue({ analysis_id: "analysis-123", frames: [] });
    mockedStartTracking.mockResolvedValue(makeTrackingResponse());
    mockedGetPlayers.mockResolvedValue(
      makePlayersResponse({
        track_summaries: [
          makeTrackSummary({ track_id: 1 }),
          makeTrackSummary({
            track_id: 99,
            eligible_for_selection: false,
            rejection_reasons: ["too few observations"],
          }),
        ],
      }),
    );

    renderWithQueryClient(<MatchDetails analysisId="analysis-123" />);
    await user.click(await screen.findByText("Advanced settings"));
    await user.selectOptions(await screen.findByLabelText("Detector backend"), "controlled-json");
    await user.click(screen.getByRole("button", { name: /find players/i }));

    await waitFor(() =>
      expect(mockedStartTracking).toHaveBeenCalledWith("analysis-123", {
        calibration_id: "auto-court-detection",
        backend: "controlled-json",
        detections_jsonl: "uploads/detections.jsonl",
        frame_interval: 1,
      }),
    );
    expect(await screen.findByText("Player 1")).toBeInTheDocument();
    expect(screen.queryByText("Track 1")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /this is me/i })).toBeInTheDocument();
  });

  it("shows a recoverable no-selectable-players state", async () => {
    mockedGetAnalysis.mockResolvedValue(makeTrackedJob());
    mockedGetAnalysisFrames.mockResolvedValue({ analysis_id: "analysis-123", frames: [] });
    mockedGetPlayers.mockResolvedValue(
      makePlayersResponse({
        track_summaries: [
          makeTrackSummary({
            track_id: 7,
            eligible_for_selection: false,
            rejection_reasons: ["mostly_outside_detected_court"],
          }),
        ],
      }),
    );

    renderWithQueryClient(<MatchDetails analysisId="analysis-123" />);

    expect(await screen.findByText("No selectable players were found.")).toBeInTheDocument();
    expect(
      screen.getByText("Try finding players again with adjusted processing options."),
    ).toBeInTheDocument();
    expect(screen.getByText("mostly_outside_detected_court")).not.toBeVisible();
  });

  it("shows tracking failures with useful copy and retry", async () => {
    const user = userEvent.setup();
    mockedGetAnalysis.mockResolvedValue(makeCalibratedJob());
    mockedGetAnalysisFrames.mockResolvedValue({ analysis_id: "analysis-123", frames: [] });
    mockedStartTracking
      .mockRejectedValueOnce(new Court4ApiError("No detections were returned.", { code: "tracking_failed" }))
      .mockReturnValue(new Promise(() => {}));

    renderWithQueryClient(<MatchDetails analysisId="analysis-123" />);
    await user.click(await screen.findByRole("button", { name: /find players/i }));

    expect(await screen.findByText("We could not identify the players")).toBeInTheDocument();
    expect(
      screen.getByText("Try the analysis again or open advanced settings to adjust processing options."),
    ).toBeInTheDocument();
    expect(screen.getByText("No detections were returned.")).not.toBeVisible();

    await user.click(screen.getByRole("button", { name: /try again/i }));
    expect(mockedStartTracking).toHaveBeenCalledTimes(2);
  });

  it("shows a typed missing-model error without leaving tracking stuck", async () => {
    const user = userEvent.setup();
    mockedGetAnalysis.mockResolvedValue(makeCalibratedJob());
    mockedGetAnalysisFrames.mockResolvedValue({ analysis_id: "analysis-123", frames: [] });
    mockedStartTracking.mockRejectedValue(
      new Court4ApiError("Player detection is not available because the detector model is missing.", {
        code: "detector_model_missing",
        status: 400,
      }),
    );

    renderWithQueryClient(<MatchDetails analysisId="analysis-123" />);
    await user.click(await screen.findByRole("button", { name: /find players/i }));

    expect(await screen.findByText("Player detection model is missing")).toBeInTheDocument();
    expect(
      screen.getAllByText(
        "Player detection is not available because the detector model is missing.",
      ),
    ).toHaveLength(2);
    expect(screen.getByRole("button", { name: /find players/i })).not.toBeDisabled();
    expect(screen.getByText("detector_model_missing")).not.toBeVisible();
  });

  it("highlights the selected player and allows changing selection", async () => {
    const user = userEvent.setup();
    const tracks = [makeTrackSummary({ track_id: 1 }), makeTrackSummary({ track_id: 2 })];
    mockedGetAnalysis.mockResolvedValue(makePlayerSelectedJob());
    mockedGetAnalysisFrames.mockResolvedValue({ analysis_id: "analysis-123", frames: [] });
    mockedGetPlayers.mockResolvedValue(
      makePlayersResponse({
        track_summaries: tracks,
        selected_player_track_id: 1,
      }),
    );
    mockedSelectPlayer.mockResolvedValue(makePlayerSelectionResponse());

    renderWithQueryClient(<MatchDetails analysisId="analysis-123" />);

    expect(await screen.findByText("You selected Player 1")).toBeInTheDocument();
    const playerTwoCard = screen.getByText("Player 2").closest("article");
    expect(playerTwoCard).not.toBeNull();
    await user.click(within(playerTwoCard as HTMLElement).getByRole("button", { name: /this is me/i }));

    await waitFor(() => expect(mockedSelectPlayer).toHaveBeenCalledWith("analysis-123", 2));
  });

  it("generates Match IQ after player selection", async () => {
    const user = userEvent.setup();
    mockedGetAnalysis.mockResolvedValue(makePlayerSelectedJob());
    mockedGetAnalysisFrames.mockResolvedValue({ analysis_id: "analysis-123", frames: [] });
    mockedGetPlayers.mockResolvedValue(makePlayersResponse({ selected_player_track_id: 1 }));
    mockedGenerateAnalytics.mockResolvedValue(makeAnalyticsGenerationResponse());

    renderWithQueryClient(<MatchDetails analysisId="analysis-123" />);

    await user.click(await screen.findByRole("button", { name: /generate my match iq/i }));

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

function makeCalibratedJob(overrides = {}) {
  return makeJob({ ...makeCalibratedFlags(), ...overrides });
}

function makeTrackedJob() {
  return makeJob({
    ...makeCalibratedFlags(),
    current_stage: "tracked",
    tracking_completed: true,
  });
}

function makePlayerSelectedJob() {
  return makeJob({
    ...makeCalibratedFlags(),
    current_stage: "player_selected",
    tracking_completed: true,
    player_selected: true,
  });
}

function makeDetectedCorners() {
  return {
    near_left: { x: 80, y: 760 },
    near_right: { x: 720, y: 760 },
    far_right: { x: 600, y: 120 },
    far_left: { x: 200, y: 120 },
  };
}
