import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { UploadRecoveryWorkspace } from "@/components/upload-recovery-workspace";
import { makeJob } from "@/test/factories";

const mocks = vi.hoisted(() => ({ discover: vi.fn(), recover: vi.fn(), resume: vi.fn(), complete: vi.fn(), cancel: vi.fn(), push: vi.fn(), wait: vi.fn(), user: { id: "owner" } }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: mocks.push }) }));
vi.mock("@/lib/auth-context", () => ({ useAuth: () => ({ user: mocks.user }) }));
vi.mock("@/components/upload-dropzone", () => ({ UploadDropzone: () => <p>New upload</p> }));
vi.mock("@/lib/api/analyses", () => ({ discoverUploads: mocks.discover, recoverUpload: mocks.recover,
  createAnalysis: mocks.resume, completeDirectUpload: mocks.complete, abortDirectUpload: mocks.cancel, waitForUploadResult: mocks.wait }));

const recovered = { upload_session_id: "8b2ee1d1-3176-4a9e-a643-66559d667e47", status: "uploading", filename: "match.mp4",
  byte_size: 6, sport: "pickleball", file_identity: `sha256-chunks-v1:${"a".repeat(64)}`,
  part_size: 3, part_count: 2, completed_parts: [{ part_number: 1, etag: '"first"', size_bytes: 3 }],
  max_concurrency: 3, max_attempts: 3, inactivity_seconds: 60, expires_at: "2099-01-01T00:00:00Z" };

describe("upload recovery workspace", () => {
  beforeEach(() => {
    vi.clearAllMocks(); mocks.user = { id: "owner" };
    mocks.discover.mockResolvedValue([recovered]); mocks.recover.mockResolvedValue(recovered);
  });

  it("restores confirmed progress after reload and asks for the original file", async () => {
    render(<UploadRecoveryWorkspace />);
    expect(await screen.findByText("Recoverable upload found")).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "50");
    expect(screen.getByRole("button", { name: "Resume upload" })).toBeDisabled();
    const file = new File(["abcdef"], "match.mp4");
    const input = screen.getByLabelText(/Original match video/);
    fireEvent.change(input, { target: { files: { item: () => file } } });
    mocks.resume.mockResolvedValue(makeJob());
    fireEvent.click(screen.getByRole("button", { name: "Resume upload" }));
    await waitFor(() => expect(mocks.resume).toHaveBeenCalledWith(file, expect.any(Function), expect.objectContaining({ resumeSessionId: recovered.upload_session_id })));
    await waitFor(() => expect(mocks.push).toHaveBeenCalled());
  });

  it("keeps existing progress after a wrong-file rejection and does not cancel", async () => {
    render(<UploadRecoveryWorkspace />);
    await screen.findByText("Recoverable upload found");
    fireEvent.change(screen.getByLabelText(/Original match video/), { target: { files: { item: () => new File(["wrong!"], "match.mp4") } } });
    mocks.resume.mockRejectedValue(new Error("Select the original video to resume this upload."));
    fireEvent.click(screen.getByRole("button", { name: "Resume upload" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Select the original video");
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "50");
    expect(mocks.cancel).not.toHaveBeenCalled();
  });

  it("finalizes all confirmed parts without asking for a file", async () => {
    const all = { ...recovered, completed_parts: [...recovered.completed_parts, { part_number: 2, etag: '"second"', size_bytes: 3 }] };
    mocks.discover.mockResolvedValue([all]); mocks.recover.mockResolvedValue(all); mocks.complete.mockResolvedValue(makeJob());
    render(<UploadRecoveryWorkspace />);
    fireEvent.click(await screen.findByRole("button", { name: "Finish upload" }));
    await waitFor(() => expect(mocks.complete).toHaveBeenCalledWith(all.upload_session_id, all.completed_parts, 6, expect.any(Function), expect.any(AbortSignal)));
    expect(mocks.resume).not.toHaveBeenCalled();
  });

  it("requires explicit cancellation and only clears UI after confirmation", async () => {
    mocks.cancel.mockResolvedValue(false);
    render(<UploadRecoveryWorkspace />);
    fireEvent.click(await screen.findByRole("button", { name: "Cancel upload" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("could not be canceled");
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "50");
    mocks.cancel.mockResolvedValue(true); mocks.discover.mockResolvedValue([]);
    fireEvent.click(screen.getByRole("button", { name: "Cancel upload" }));
    expect(await screen.findByText("New upload")).toBeInTheDocument();
  });

  it("never shows a previous owner's upload after an account switch", async () => {
    const view = render(<UploadRecoveryWorkspace />);
    await screen.findByText("match.mp4");
    mocks.user = { id: "different-owner" };
    mocks.discover.mockResolvedValue([]);
    view.rerender(<UploadRecoveryWorkspace />);
    expect(screen.queryByText("match.mp4")).not.toBeInTheDocument();
    expect(await screen.findByText("New upload")).toBeInTheDocument();
  });
});
