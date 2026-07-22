import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ManualCalibrationWorkspace } from "@/components/manual-calibration-workspace";
import { getAnalysisFrames, submitCalibration } from "@/lib/api/analyses";
import { makeCalibrationResponse, makeFrame } from "@/test/factories";
import { renderWithQueryClient } from "@/test/render";

vi.mock("@/lib/api/analyses", () => ({
  getAnalysisFrames: vi.fn(),
  submitCalibration: vi.fn(),
}));

const mockedGetAnalysisFrames = vi.mocked(getAnalysisFrames);
const mockedSubmitCalibration = vi.mocked(submitCalibration);

describe("manual calibration workspace", () => {
  beforeEach(() => {
    mockedGetAnalysisFrames.mockReset();
    mockedSubmitCalibration.mockReset();
  });

  it("selects four scaled points and submits them in backend order", async () => {
    const user = userEvent.setup();
    mockedGetAnalysisFrames.mockResolvedValue({
      analysis_id: "analysis-123",
      frames: [makeFrame()],
    });
    mockedSubmitCalibration.mockResolvedValue(makeCalibrationResponse());

    renderWithQueryClient(<ManualCalibrationWorkspace analysisId="analysis-123" />);

    const image = await screen.findByRole("img", { name: "Manual calibration frame" });
    setImageGeometry(image, { width: 400, height: 450, naturalWidth: 800, naturalHeight: 900 });
    fireEvent.load(image);

    clickImage(image, 100, 60);
    clickImage(image, 300, 60);
    clickImage(image, 360, 380);
    clickImage(image, 40, 380);

    expect(screen.queryByText(/mark .* next/i)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /save manual calibration/i }));

    await waitFor(() =>
      expect(mockedSubmitCalibration).toHaveBeenCalledWith("analysis-123", {
        calibration_id: "manual-calibration",
        source_frame: "frames/frame_000001.jpg",
        near_left: { x: 80, y: 760 },
        near_right: { x: 720, y: 760 },
        far_right: { x: 600, y: 120 },
        far_left: { x: 200, y: 120 },
      }),
    );
    expect(await screen.findByText("Manual calibration saved")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Verification artifact" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Top-down court artifact" })).toBeInTheDocument();
  });

  it("supports undo and reset", async () => {
    const user = userEvent.setup();
    mockedGetAnalysisFrames.mockResolvedValue({
      analysis_id: "analysis-123",
      frames: [makeFrame()],
    });

    renderWithQueryClient(<ManualCalibrationWorkspace analysisId="analysis-123" />);

    const image = await screen.findByRole("img", { name: "Manual calibration frame" });
    setImageGeometry(image, { width: 400, height: 450, naturalWidth: 800, naturalHeight: 900 });
    fireEvent.load(image);
    clickImage(image, 100, 60);
    clickImage(image, 300, 60);

    await user.click(screen.getByRole("button", { name: /undo/i }));
    expect(screen.getByText("Mark far right next.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /reset/i }));
    expect(screen.getByText("Mark far left next.")).toBeInTheDocument();
  });

  it("prevents invalid self-intersecting polygons from being submitted", async () => {
    mockedGetAnalysisFrames.mockResolvedValue({
      analysis_id: "analysis-123",
      frames: [makeFrame()],
    });

    renderWithQueryClient(<ManualCalibrationWorkspace analysisId="analysis-123" />);

    const image = await screen.findByRole("img", { name: "Manual calibration frame" });
    setImageGeometry(image, { width: 400, height: 450, naturalWidth: 800, naturalHeight: 900 });
    fireEvent.load(image);
    clickImage(image, 100, 60);
    clickImage(image, 300, 60);
    clickImage(image, 40, 380);
    clickImage(image, 360, 380);

    expect(
      screen.getByText("The selected corners must form one non-crossing court polygon."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /save manual calibration/i })).toBeDisabled();
    expect(mockedSubmitCalibration).not.toHaveBeenCalled();
  });
});

function setImageGeometry(
  image: HTMLElement,
  {
    width,
    height,
    naturalWidth,
    naturalHeight,
  }: {
    width: number;
    height: number;
    naturalWidth: number;
    naturalHeight: number;
  },
) {
  Object.defineProperty(image, "naturalWidth", { configurable: true, value: naturalWidth });
  Object.defineProperty(image, "naturalHeight", { configurable: true, value: naturalHeight });
  image.getBoundingClientRect = () =>
    ({
      x: 0,
      y: 0,
      left: 0,
      top: 0,
      right: width,
      bottom: height,
      width,
      height,
      toJSON: () => ({}),
    }) as DOMRect;
}

function clickImage(image: HTMLElement, clientX: number, clientY: number) {
  fireEvent.click(image, { clientX, clientY });
}
