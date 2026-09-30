import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MatchDetails } from "@/components/match-details";
import { Court4ApiError } from "@/lib/api/client";
import {
  detectCourt,
  generateAnalytics,
  getAnalysis,
  getAnalysisFrames,
  getPlayerCandidates,
  mergePlayerCandidates,
  rejectPlayerCandidate,
  restorePlayerCandidate,
  selectPlayerCandidate,
  startTracking,
  unmergePlayerCandidate,
} from "@/lib/api/analyses";
import {
  makeAnalyticsGenerationResponse,
  makeArtifact,
  makeCourtDetectionResponse,
  makeFrame,
  makeJob,
  makePlayerCandidate,
  makePlayerCandidateCollection,
  makeRecordingQuality,
  makeTrackingResponse,
} from "@/test/factories";
import { renderWithQueryClient } from "@/test/render";

const pushMock = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api/source-media", () => ({
  getMatchLifecycle: vi.fn(async () => ({ analysis_id: "analysis-123", state: "live" })),
  deleteMatch: vi.fn(), deleteSourceVideo: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

vi.mock("@/lib/api/analyses", () => ({
  detectCourt: vi.fn(),
  generateAnalytics: vi.fn(),
  getAnalysis: vi.fn(),
  getAnalysisFrames: vi.fn(),
  getPlayerCandidates: vi.fn(),
  mergePlayerCandidates: vi.fn(),
  rejectPlayerCandidate: vi.fn(),
  restorePlayerCandidate: vi.fn(),
  selectPlayerCandidate: vi.fn(),
  startTracking: vi.fn(),
  unmergePlayerCandidate: vi.fn(),
}));

const mockedDetectCourt = vi.mocked(detectCourt);
const mockedGenerateAnalytics = vi.mocked(generateAnalytics);
const mockedGetAnalysis = vi.mocked(getAnalysis);
const mockedGetAnalysisFrames = vi.mocked(getAnalysisFrames);
const mockedGetPlayerCandidates = vi.mocked(getPlayerCandidates);
const mockedMergePlayerCandidates = vi.mocked(mergePlayerCandidates);
const mockedRejectPlayerCandidate = vi.mocked(rejectPlayerCandidate);
const mockedRestorePlayerCandidate = vi.mocked(restorePlayerCandidate);
const mockedSelectPlayerCandidate = vi.mocked(selectPlayerCandidate);
const mockedStartTracking = vi.mocked(startTracking);
const mockedUnmergePlayerCandidate = vi.mocked(unmergePlayerCandidate);

describe("match details workflow", () => {
  beforeEach(() => {
    pushMock.mockClear();
    mockedDetectCourt.mockReset();
    mockedGenerateAnalytics.mockReset();
    mockedGetAnalysis.mockReset();
    mockedGetAnalysisFrames.mockReset();
    mockedGetPlayerCandidates.mockReset();
    mockedMergePlayerCandidates.mockReset();
    mockedRejectPlayerCandidate.mockReset();
    mockedRestorePlayerCandidate.mockReset();
    mockedSelectPlayerCandidate.mockReset();
    mockedStartTracking.mockReset();
    mockedUnmergePlayerCandidate.mockReset();
  });

  it("shows a loading state while the analysis is loading", () => {
    mockedGetAnalysis.mockReturnValue(new Promise(() => {}));

    renderWithQueryClient(<MatchDetails analysisId="analysis-123" />);

    expect(
      screen.getByRole("status", { name: "Loading match details" }),
    ).toBeInTheDocument();
  });

  it("shows an honest Padel experimental state without Pickleball workflow actions", async () => {
    mockedGetAnalysis.mockResolvedValue(makeJob({ sport: "padel" }));
    mockedGetAnalysisFrames.mockResolvedValue({ analysis_id: "analysis-123", frames: [] });

    renderWithQueryClient(<MatchDetails analysisId="analysis-123" />);

    expect(await screen.findByText("Video inspection complete")).toBeInTheDocument();
    expect(screen.getAllByText(/Padel — Experimental/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/will never use Pickleball interpretation rules/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /recognize court/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /generate my match iq/i })).not.toBeInTheDocument();
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
      screen.getByText("Court4 is temporarily unavailable. Check your connection and try again."),
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

  it("shows the useful court verification without developer-facing artifacts or metadata", async () => {
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

    expect(await screen.findByText("91% confidence")).toBeInTheDocument();
    expect(await screen.findByText("Find the players")).toBeInTheDocument();
    const courtRecognition = screen.getByRole("region", { name: "Court recognized" });
    const playerTracking = within(courtRecognition).getByRole("region", {
      name: "Find the players",
    });
    expect(playerTracking).toBeInTheDocument();
    expect(within(playerTracking).getByText("Next step")).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /continue to find players/i }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Detected court" })).toBeInTheDocument();
    expect(screen.queryByText("Detected court")).not.toBeInTheDocument();
    expect(screen.queryByRole("img", { name: "Top-down court view" })).not.toBeInTheDocument();
    expect(screen.queryByText("Confidence value")).not.toBeInTheDocument();
    expect(screen.queryByText("Calibration source")).not.toBeInTheDocument();
    expect(screen.queryByText("Technical details")).not.toBeInTheDocument();
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

    expect(await screen.findByText("91% confidence")).toBeInTheDocument();
    expect(screen.queryByText("Detection confidence")).not.toBeInTheDocument();
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

  it("distinguishes unavailable frames from a saved geometric failure and permits retry", async () => {
    const user = userEvent.setup();
    mockedGetAnalysis.mockResolvedValue(makeJob({
      court_detection_status: "failed", court_detection_confidence: 0,
      manual_calibration_required: true,
    }));
    mockedGetAnalysisFrames.mockResolvedValue({ analysis_id: "analysis-123", frames: [] });
    mockedDetectCourt.mockRejectedValue(new Court4ApiError("Frames unavailable", {
      code: "recognition_frames_unavailable", status: 409,
    }));
    renderWithQueryClient(<MatchDetails analysisId="analysis-123" />);
    await user.click(await screen.findByRole("button", { name: /recognize court/i }));
    expect(await screen.findByText("Inspection frames unavailable")).toBeInTheDocument();
    expect(screen.getByText(/could not access usable inspection frames/)).toBeInTheDocument();
    expect(screen.queryByText(/Confidence was 0%/)).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /calibrate manually/i })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /try again/i }));
    expect(mockedDetectCourt).toHaveBeenCalledTimes(2);
    expect(pushMock).not.toHaveBeenCalled();
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

  it("keeps developer-facing tracking options out of the user view", async () => {
    mockedGetAnalysis.mockResolvedValue(makeCalibratedJob());
    mockedGetAnalysisFrames.mockResolvedValue({ analysis_id: "analysis-123", frames: [] });

    renderWithQueryClient(<MatchDetails analysisId="analysis-123" />);

    expect(await screen.findByText("Find the players")).toBeInTheDocument();
    expect(screen.queryByText("Advanced settings")).not.toBeInTheDocument();
    expect(screen.queryByText("Detector backend")).not.toBeInTheDocument();
    expect(screen.queryByText("Frame interval")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /find players/i })).toBeInTheDocument();
  });

  it("shows time-based player-tracking progress without duplicate controls", async () => {
    const user = userEvent.setup();
    mockedGetAnalysis.mockResolvedValue(makeCalibratedJob());
    mockedGetAnalysisFrames.mockResolvedValue({ analysis_id: "analysis-123", frames: [] });
    mockedStartTracking.mockReturnValue(new Promise(() => {}));

    renderWithQueryClient(<MatchDetails analysisId="analysis-123" />);
    await user.click(await screen.findByRole("button", { name: /find players/i }));

    expect(mockedStartTracking).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("button", { name: /find players/i })).not.toBeInTheDocument();
    expect(screen.getByText("Analyzing player movement")).toBeInTheDocument();
    expect(screen.getByText("1%")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Player tracking progress" })).toHaveAttribute(
      "aria-valuenow",
      "1",
    );
    expect(screen.queryByText("Tracking player movement now.")).not.toBeInTheDocument();
  });

  it("starts tracking with automatic defaults and displays eligible player cards", async () => {
    const user = userEvent.setup();
    mockedGetAnalysis
      .mockResolvedValueOnce(makeCalibratedJob())
      .mockResolvedValue(makeTrackedJob());
    mockedGetAnalysisFrames.mockResolvedValue({ analysis_id: "analysis-123", frames: [] });
    mockedStartTracking.mockResolvedValue(makeTrackingResponse());
    mockedGetPlayerCandidates.mockResolvedValue(
      makePlayerCandidateCollection({
        candidates: [
          makePlayerCandidate(),
          makePlayerCandidate({
            candidate_id: "pc-needs-review",
            source_raw_track_ids: [99],
            quality: "UNCERTAIN",
            quality_reasons: ["short_track_duration"],
            warnings: ["short_track_duration"],
          }),
        ],
      }),
    );

    renderWithQueryClient(<MatchDetails analysisId="analysis-123" />);
    await user.click(await screen.findByRole("button", { name: /find players/i }));

    await waitFor(() =>
      expect(mockedStartTracking).toHaveBeenCalledWith("analysis-123", {
        calibration_id: "auto-court-detection",
        backend: "ultralytics",
        detections_jsonl: null,
        frame_interval: 1,
      }),
    );
    expect(await screen.findByText("Player 1")).toBeInTheDocument();
    expect(screen.getByText("100%")).toBeInTheDocument();
    expect(screen.queryByText("Track 1")).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /this is me/i })).toHaveLength(2);
  });

  it("shows a recoverable no-selectable-players state", async () => {
    mockedGetAnalysis.mockResolvedValue(makeTrackedJob());
    mockedGetAnalysisFrames.mockResolvedValue({ analysis_id: "analysis-123", frames: [] });
    mockedGetPlayerCandidates.mockResolvedValue(
      makePlayerCandidateCollection({ candidates: [] }),
    );

    renderWithQueryClient(<MatchDetails analysisId="analysis-123" />);

    expect(
      await screen.findByText(
        "Court4 found people in the video, but none were tracked long enough to analyze reliably.",
      ),
    ).toBeInTheDocument();
  });

  it("keeps a confirmed selection through a later 429 candidate refresh", async () => {
    const user = userEvent.setup();
    const initial = makePlayerCandidateCollection();
    const saved = makePlayerCandidateCollection({
      selected_candidate_id: initial.candidates[0].candidate_id,
    });
    mockedGetAnalysis.mockResolvedValue(makePlayerSelectedJob());
    mockedGetAnalysisFrames.mockResolvedValue({ analysis_id: "analysis-123", frames: [] });
    mockedGetPlayerCandidates.mockResolvedValueOnce(initial).mockRejectedValue(
      new Court4ApiError("Temporary processing workspace capacity is unavailable.", {
        code: "processing_workspace_unavailable", status: 429,
      }),
    );
    mockedSelectPlayerCandidate.mockResolvedValue(saved);
    const { queryClient } = renderWithQueryClient(<MatchDetails analysisId="analysis-123" />);
    await user.click(await screen.findByRole("button", { name: /this is me/i }));

    expect(await screen.findByText("You selected Player 1")).toBeInTheDocument();
    await waitFor(() => expect(mockedGetAnalysis).toHaveBeenCalledTimes(2));
    expect(mockedGetPlayerCandidates).toHaveBeenCalledTimes(1);
    expect(mockedGetAnalysisFrames).toHaveBeenCalledTimes(1);
    expect(queryClient.getQueryData(["analysis", "analysis-123", "player-candidates"])).toEqual(saved);

    await act(async () => {
      await queryClient.invalidateQueries({
        queryKey: ["analysis", "analysis-123", "player-candidates"], exact: true,
      });
    });
    expect(await screen.findByText("Player details could not be refreshed")).toBeInTheDocument();
    expect(screen.getByText("You selected Player 1")).toBeInTheDocument();
    expect(screen.getByText("Player 1")).toBeInTheDocument();
    expect(screen.queryByText("We could not identify the players")).not.toBeInTheDocument();
    expect(queryClient.getQueryData(["analysis", "analysis-123", "player-candidates"])).toEqual(saved);
  });

  it("does not let an older in-flight candidate refresh replace a saved selection", async () => {
    const user = userEvent.setup();
    const initial = makePlayerCandidateCollection();
    const saved = makePlayerCandidateCollection({
      selected_candidate_id: initial.candidates[0].candidate_id,
    });
    let finishRefresh!: (value: typeof initial) => void;
    mockedGetAnalysis.mockResolvedValue(makePlayerSelectedJob());
    mockedGetAnalysisFrames.mockResolvedValue({ analysis_id: "analysis-123", frames: [] });
    mockedGetPlayerCandidates.mockResolvedValueOnce(initial).mockReturnValueOnce(
      new Promise((resolve) => { finishRefresh = resolve; }),
    );
    mockedSelectPlayerCandidate.mockResolvedValue(saved);
    const { queryClient } = renderWithQueryClient(<MatchDetails analysisId="analysis-123" />);
    await screen.findByText("Player 1");
    act(() => {
      void queryClient.invalidateQueries({
        queryKey: ["analysis", "analysis-123", "player-candidates"], exact: true,
      });
    });
    await waitFor(() => expect(mockedGetPlayerCandidates).toHaveBeenCalledTimes(2));
    await user.click(screen.getByRole("button", { name: /this is me/i }));
    expect(await screen.findByText("You selected Player 1")).toBeInTheDocument();
    await act(async () => { finishRefresh(initial); });
    expect(queryClient.getQueryData(["analysis", "analysis-123", "player-candidates"])).toEqual(saved);
    expect(screen.getByText("You selected Player 1")).toBeInTheDocument();
  });

  it("keeps candidates and reports a save failure without claiming a selection", async () => {
    const user = userEvent.setup();
    const initial = makePlayerCandidateCollection();
    mockedGetAnalysis.mockResolvedValue(makeTrackedJob());
    mockedGetAnalysisFrames.mockResolvedValue({ analysis_id: "analysis-123", frames: [] });
    mockedGetPlayerCandidates.mockResolvedValue(initial);
    mockedSelectPlayerCandidate.mockRejectedValue(
      new Court4ApiError("Player candidate selection failed.", {
        code: "candidate_selection_failed", status: 400,
      }),
    );
    const { queryClient } = renderWithQueryClient(<MatchDetails analysisId="analysis-123" />);
    await user.click(await screen.findByRole("button", { name: /this is me/i }));
    expect(await screen.findByText("Court4 could not save the candidate review")).toBeInTheDocument();
    expect(screen.getByText("Player 1")).toBeInTheDocument();
    expect(screen.queryByText("You selected Player 1")).not.toBeInTheDocument();
    expect(screen.queryByText("We could not identify the players")).not.toBeInTheDocument();
    expect(queryClient.getQueryData(["analysis", "analysis-123", "player-candidates"])).toEqual(initial);
    expect(mockedGetPlayerCandidates).toHaveBeenCalledTimes(1);
  });

  it("distinguishes a candidate load failure from a successful empty collection", async () => {
    mockedGetAnalysis.mockResolvedValue(makeTrackedJob());
    mockedGetAnalysisFrames.mockResolvedValue({ analysis_id: "analysis-123", frames: [] });
    mockedGetPlayerCandidates.mockRejectedValue(
      new Court4ApiError("Temporary processing workspace capacity is unavailable.", {
        code: "processing_workspace_unavailable", status: 429,
      }),
    );
    renderWithQueryClient(<MatchDetails analysisId="analysis-123" />);
    expect(await screen.findByText("Player details could not be loaded")).toBeInTheDocument();
    expect(screen.queryByText("We could not identify the players")).not.toBeInTheDocument();
    expect(screen.queryByText(/none were tracked long enough/)).not.toBeInTheDocument();
  });

  it("does not keep showing cached candidates after an access-denied refresh", async () => {
    mockedGetAnalysis.mockResolvedValue(makeTrackedJob());
    mockedGetAnalysisFrames.mockResolvedValue({ analysis_id: "analysis-123", frames: [] });
    mockedGetPlayerCandidates.mockResolvedValueOnce(makePlayerCandidateCollection()).mockRejectedValue(
      new Court4ApiError("Access denied.", { code: "forbidden", status: 403 }),
    );
    const { queryClient } = renderWithQueryClient(<MatchDetails analysisId="analysis-123" />);
    await screen.findByText("Player 1");
    await act(async () => {
      await queryClient.invalidateQueries({
        queryKey: ["analysis", "analysis-123", "player-candidates"], exact: true,
      });
    });
    expect(await screen.findByText("Player details could not be loaded")).toBeInTheDocument();
    expect(screen.queryByText("Player 1")).not.toBeInTheDocument();
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
      screen.getByText("Try the analysis again. If the problem continues, use a clearer video."),
    ).toBeInTheDocument();
    expect(screen.queryByText("No detections were returned.")).not.toBeInTheDocument();

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
      screen.getByText(
        "Player detection is not available because the detector model is missing.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /find players/i })).not.toBeDisabled();
    expect(screen.queryByText("detector_model_missing")).not.toBeInTheDocument();
  });

  it("highlights the selected player and allows changing selection", async () => {
    const user = userEvent.setup();
    const candidates = [
      makePlayerCandidate(),
      makePlayerCandidate({
        candidate_id: "pc-player-two",
        source_raw_track_ids: [2],
      }),
    ];
    mockedGetAnalysis.mockResolvedValue(makePlayerSelectedJob());
    mockedGetAnalysisFrames.mockResolvedValue({ analysis_id: "analysis-123", frames: [] });
    mockedGetPlayerCandidates.mockResolvedValue(
      makePlayerCandidateCollection({
        candidates,
        selected_candidate_id: "pc-player-one",
      }),
    );
    mockedSelectPlayerCandidate.mockResolvedValue(
      makePlayerCandidateCollection({
        candidates,
        selected_candidate_id: "pc-player-two",
      }),
    );

    renderWithQueryClient(<MatchDetails analysisId="analysis-123" />);

    expect(await screen.findByText("You selected Player 1")).toBeInTheDocument();
    const playerTwoCard = screen.getByText("Player 2").closest("article");
    expect(playerTwoCard).not.toBeNull();
    await user.click(within(playerTwoCard as HTMLElement).getByRole("button", { name: /this is me/i }));

    await waitFor(() =>
      expect(mockedSelectPlayerCandidate).toHaveBeenCalledWith(
        "analysis-123",
        "pc-player-two",
      ),
    );
  });

  it("shows at most four eligible player choices and hides automatic exclusions", async () => {
    const candidates = Array.from({ length: 5 }, (_, index) =>
      makePlayerCandidate({
        candidate_id: `pc-player-${index + 1}`,
        source_raw_track_ids: [index + 1],
      }),
    );
    mockedGetAnalysis.mockResolvedValue(makeTrackedJob());
    mockedGetAnalysisFrames.mockResolvedValue({ analysis_id: "analysis-123", frames: [] });
    mockedGetPlayerCandidates.mockResolvedValue(
      makePlayerCandidateCollection({
        candidates,
        excluded_candidates: [
          makePlayerCandidate({
            candidate_id: "pc-spectator",
            source_raw_track_ids: [99],
            selection_eligible: false,
            selection_exclusion_reasons: ["mostly_outside_detected_court"],
          }),
        ],
      }),
    );

    renderWithQueryClient(<MatchDetails analysisId="analysis-123" />);

    expect(await screen.findByText("Player 1")).toBeInTheDocument();
    expect(screen.getByText("Player 4")).toBeInTheDocument();
    expect(screen.queryByText("Player 5")).not.toBeInTheDocument();
    expect(screen.queryByText(/Excluded candidates/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /restore/i })).not.toBeInTheDocument();
  });

  it("shows candidate quality, preview, and guidance without raw lineage", async () => {
    const user = userEvent.setup();
    mockedGetAnalysis.mockResolvedValue(makeTrackedJob());
    mockedGetAnalysisFrames.mockResolvedValue({ analysis_id: "analysis-123", frames: [] });
    mockedGetPlayerCandidates.mockResolvedValue(
      makePlayerCandidateCollection({
        candidates: [
          makePlayerCandidate({
            quality: "UNCERTAIN",
            quality_reasons: ["vertical_video_limitation"],
            warnings: ["vertical_video_limitation"],
            source_raw_track_ids: [4, 12],
          }),
        ],
        recording_suitability: {
          status: "LIMITED",
          reasons: ["vertical_video_limitation"],
          guidance: ["Use landscape orientation when possible."],
          orientation: "vertical",
          detected_people: 2,
          usable_candidate_count: 0,
        },
        analysis_readiness: makeRecordingQuality({
          status: "LIMITED",
          warnings: [
            {
              code: "vertical_orientation",
              label: "Orientation",
              status: "WARNING",
              message: "Vertical framing may exclude important parts of the court.",
              measured_value: "vertical",
            },
          ],
          reason_codes: ["vertical_orientation"],
          guidance: ["Use landscape orientation when possible."],
        }),
      }),
    );

    renderWithQueryClient(<MatchDetails analysisId="analysis-123" />);

    expect(await screen.findByText("Needs review")).toBeInTheDocument();
    expect(screen.getByText("Use landscape orientation when possible.")).toBeInTheDocument();
    expect(screen.queryByText("4, 12")).not.toBeInTheDocument();
    const card = screen.getByText("Player 1").closest("article") as HTMLElement;
    await user.click(within(card).getByText("Preview candidate"));
    expect(within(card).getAllByRole("img", { name: /Player 1 at/i })).toHaveLength(3);
    expect(within(card).queryByText("Technical details")).not.toBeInTheDocument();
  });

  it("rejects and restores a candidate while keeping it recoverable", async () => {
    const user = userEvent.setup();
    const candidate = makePlayerCandidate();
    const initial = makePlayerCandidateCollection({ candidates: [candidate] });
    const rejected = makePlayerCandidateCollection({
      candidates: [],
      excluded_candidates: [
        {
          ...candidate,
          review_status: "REJECTED",
          rejection_reason: "not_a_player",
        },
      ],
    });
    mockedGetAnalysis.mockResolvedValue(makeTrackedJob());
    mockedGetAnalysisFrames.mockResolvedValue({ analysis_id: "analysis-123", frames: [] });
    mockedGetPlayerCandidates.mockResolvedValueOnce(initial).mockResolvedValue(rejected);
    mockedRejectPlayerCandidate.mockResolvedValue(rejected);
    mockedRestorePlayerCandidate.mockResolvedValue(initial);

    renderWithQueryClient(<MatchDetails analysisId="analysis-123" />);
    await user.click(await screen.findByRole("button", { name: /not a player/i }));

    expect(await screen.findByText("Excluded candidates (1)")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /restore/i })).toBeInTheDocument();
    expect(mockedRejectPlayerCandidate).toHaveBeenCalledWith(
      "analysis-123",
      "pc-player-one",
    );
  });

  it("shows a clear warning when a manual candidate merge is impossible", async () => {
    const user = userEvent.setup();
    mockedGetAnalysis.mockResolvedValue(makeTrackedJob());
    mockedGetAnalysisFrames.mockResolvedValue({ analysis_id: "analysis-123", frames: [] });
    mockedGetPlayerCandidates.mockResolvedValue(
      makePlayerCandidateCollection({
        candidates: [
          makePlayerCandidate(),
          makePlayerCandidate({
            candidate_id: "pc-player-two",
            source_raw_track_ids: [2],
          }),
        ],
      }),
    );
    mockedMergePlayerCandidates.mockRejectedValue(
      new Court4ApiError(
        "These candidates appear at the same time and cannot be merged safely.",
        { code: "impossible_candidate_merge", status: 409 },
      ),
    );

    renderWithQueryClient(<MatchDetails analysisId="analysis-123" />);
    const playerOne = (await screen.findByText("Player 1")).closest("article") as HTMLElement;
    const playerTwo = screen.getByText("Player 2").closest("article") as HTMLElement;
    await user.click(within(playerOne).getByRole("button", { name: /same player/i }));
    await user.click(within(playerTwo).getByRole("button", { name: /merge with this/i }));
    await user.click(screen.getByRole("button", { name: /confirm merge/i }));

    expect(
      await screen.findByText("These candidates cannot be merged safely"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "These candidates appear at the same time and cannot be merged safely.",
      ),
    ).toBeInTheDocument();
  });

  it("generates Match IQ after player selection", async () => {
    const user = userEvent.setup();
    mockedGetAnalysis.mockResolvedValue(makePlayerSelectedJob());
    mockedGetAnalysisFrames.mockResolvedValue({ analysis_id: "analysis-123", frames: [] });
    mockedGetPlayerCandidates.mockResolvedValue(
      makePlayerCandidateCollection({ selected_candidate_id: "pc-player-one" }),
    );
    mockedGenerateAnalytics.mockResolvedValue(makeAnalyticsGenerationResponse());

    renderWithQueryClient(<MatchDetails analysisId="analysis-123" />);

    const playerChoices = await screen.findByRole("group", {
      name: "Player choices and Match IQ",
    });
    const matchIQ = screen.getByRole("region", { name: "Generate your Match IQ" });
    const selectedPlayer = within(playerChoices).getByText("Player 1").closest("article");
    expect(within(playerChoices).getByRole("region", { name: "Generate your Match IQ" })).toBe(
      matchIQ,
    );
    expect(selectedPlayer?.nextElementSibling).toBe(matchIQ);

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
