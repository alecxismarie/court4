import { act, fireEvent, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CalibrationReview } from "@/components/calibration-review";
import { MatchWorkflow } from "@/components/workflow-actions";
import { confirmCalibration } from "@/lib/api/analyses";
import { makeJob } from "@/test/factories";
import { renderWithQueryClient } from "@/test/render";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/lib/api/analyses", async (original) => ({
  ...await original<typeof import("@/lib/api/analyses")>(),
  confirmCalibration: vi.fn(),
}));

const proposed = () => makeJob({
  calibration_completed: true, calibration_verified: false,
  active_calibration_id: "automatic", calibration_checksum_sha256: "a".repeat(64),
});

describe("calibration verification", () => {
  beforeEach(() => { vi.mocked(confirmCalibration).mockReset(); });
  it("shows the overlay and blocks player controls until verified", async () => {
    await act(async () => { renderWithQueryClient(<MatchWorkflow job={proposed()} />); });
    expect(screen.getByRole("img", { name: "Court calibration overlay for review" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Looks correct" })).toBeDisabled();
    expect(screen.getByRole("link", { name: "Adjust court" })).toHaveAttribute("href", "/matches/analysis-123/calibrate");
    expect(screen.queryByRole("button", { name: "Find Players" })).not.toBeInTheDocument();
  });
  it("confirms the exact displayed calibration and preserves verified state on reload", async () => {
    const user = userEvent.setup();
    const verified = { ...proposed(), calibration_verified: true };
    vi.mocked(confirmCalibration).mockResolvedValue(verified);
    const view = renderWithQueryClient(<CalibrationReview job={proposed()} />);
    fireEvent.load(screen.getByRole("img", { name: "Court calibration overlay for review" }));
    await user.click(screen.getByRole("button", { name: "Looks correct" }));
    expect(await screen.findByText("Court verified for measurements")).toBeInTheDocument();
    expect(confirmCalibration).toHaveBeenCalledWith("analysis-123", "automatic", "a".repeat(64));
    view.unmount();
    await act(async () => { renderWithQueryClient(<CalibrationReview job={verified} />); });
    expect(screen.queryByRole("button", { name: "Looks correct" })).not.toBeInTheDocument();
    expect(screen.getByText("Court verified for measurements")).toBeInTheDocument();
  });
  it("keeps a failed confirmation unverified", async () => {
    vi.mocked(confirmCalibration).mockRejectedValue(new Error("The court changed. Reload it."));
    renderWithQueryClient(<CalibrationReview job={proposed()} />);
    fireEvent.load(screen.getByRole("img", { name: "Court calibration overlay for review" }));
    await userEvent.setup().click(screen.getByRole("button", { name: "Looks correct" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The court changed");
    expect(screen.getByRole("button", { name: "Looks correct" })).toBeInTheDocument();
  });
});
