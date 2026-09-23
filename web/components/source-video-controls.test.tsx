import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SourceVideoControls } from "@/components/source-video-controls";
import { deleteSourceVideo } from "@/lib/api/source-media";
import { makeJob } from "@/test/factories";
import { renderWithQueryClient } from "@/test/render";

vi.mock("@/lib/api/source-media", () => ({ deleteSourceVideo: vi.fn() }));
const completed = () => makeJob({ status: "completed", analytics_completed: true });

describe("media-only deletion", () => {
  beforeEach(() => { vi.mocked(deleteSourceVideo).mockReset(); });

  it("requires deliberate confirmation and waits for backend success", async () => {
    const user = userEvent.setup();
    let confirm!: () => void;
    vi.mocked(deleteSourceVideo).mockImplementation(() => new Promise<void>((resolve) => { confirm = resolve; }));
    renderWithQueryClient(<SourceVideoControls job={completed()} />);
    await user.click(screen.getByRole("button", { name: "Delete video" }));
    expect(deleteSourceVideo).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toHaveTextContent("Your completed analysis and Progress history will remain");
    await user.click(screen.getByRole("button", { name: "Keep video" }));
    expect(deleteSourceVideo).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Delete video" }));
    await user.click(screen.getByRole("button", { name: "Permanently delete video" }));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Deleting video…" })).toBeDisabled();
    confirm();
    expect(await screen.findByRole("status")).toHaveTextContent("Source video deleted");
    expect(deleteSourceVideo).toHaveBeenCalledWith("analysis-123");
    expect(screen.queryByRole("button", { name: "Delete video" })).not.toBeInTheDocument();
  });

  it("keeps errors retryable without claiming success", async () => {
    const user = userEvent.setup();
    vi.mocked(deleteSourceVideo).mockRejectedValueOnce(new Error("Storage unavailable"))
      .mockResolvedValueOnce(undefined);
    renderWithQueryClient(<SourceVideoControls job={completed()} />);
    await user.click(screen.getByRole("button", { name: "Delete video" }));
    await user.click(screen.getByRole("button", { name: "Permanently delete video" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Storage unavailable");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Permanently delete video" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Source video deleted"));
  });

  it("shows durable deletion and hides deletion for unfinished analysis", () => {
    const view = renderWithQueryClient(<SourceVideoControls job={makeJob()} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    view.unmount();
    renderWithQueryClient(<SourceVideoControls job={makeJob({ ...completed(), source_media_state: "deleted" })} />);
    expect(screen.getByRole("status")).toHaveTextContent("Source video deleted");
  });
});
