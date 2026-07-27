import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { UploadDropzone, type UploadAnalysisFn } from "@/components/upload-dropzone";
import type { AnalysisJob } from "@/lib/api/types";
import { makeJob } from "@/test/factories";
import { renderWithQueryClient } from "@/test/render";

const pushMock = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({
  usePathname: () => "/matches/upload",
  useRouter: () => ({ push: pushMock }),
}));

describe("upload dropzone", () => {
  beforeEach(() => {
    pushMock.mockClear();
    window.localStorage.clear();
    process.env.NEXT_PUBLIC_COURT4_MAX_UPLOAD_BYTES = "1073741824";
  });

  it("shows the video guide before upload", () => {
    renderWithQueryClient(<UploadDropzone />);

    expect(screen.getByText("How to make a clear Court4 video")).toBeInTheDocument();
    expect(screen.getByText(/behind or diagonally behind the baseline/i)).toBeInTheDocument();
    expect(screen.getByText(/720p minimum; 1080p is recommended/i)).toBeInTheDocument();
    expect(screen.getByText(/Usable tracked time matters more/i)).toBeInTheDocument();
  });

  it("validates selected video size before upload", async () => {
    const user = userEvent.setup();
    const uploadAnalysis = vi.fn<UploadAnalysisFn>();
    process.env.NEXT_PUBLIC_COURT4_MAX_UPLOAD_BYTES = "1";

    renderWithQueryClient(<UploadDropzone uploadAnalysis={uploadAnalysis} />);

    await user.upload(
      screen.getByLabelText("Match video file"),
      new File(["not a video"], "match.mp4", { type: "video/mp4" }),
    );
    await user.click(screen.getByRole("button", { name: /upload selected video/i }));

    expect(await screen.findByText("Selected video is too large.")).toBeInTheDocument();
    expect(uploadAnalysis).not.toHaveBeenCalled();
  });

  it("uploads a valid video, stores the analysis id, and reports progress", async () => {
    const user = userEvent.setup();
    const file = new File(["video"], "match.mp4", { type: "video/mp4" });
    const onUploadComplete = vi.fn();
    const uploadAnalysis = vi.fn<UploadAnalysisFn>(async (_file, onProgress) => {
      onProgress?.({ loaded: file.size, total: file.size, percent: 100 });
      return makeJob({ analysis_id: "analysis-ok" });
    });

    renderWithQueryClient(
      <UploadDropzone
        uploadAnalysis={uploadAnalysis}
        onUploadComplete={onUploadComplete}
      />,
    );

    await user.upload(screen.getByLabelText("Match video file"), file);
    await user.click(screen.getByRole("button", { name: /upload selected video/i }));

    await waitFor(() => expect(uploadAnalysis).toHaveBeenCalledWith(file, expect.any(Function)));
    expect(await screen.findByText("100% uploaded")).toBeInTheDocument();
    await waitFor(() => expect(onUploadComplete).toHaveBeenCalledWith(makeJob({ analysis_id: "analysis-ok" })));
    expect(JSON.parse(window.localStorage.getItem("court4.recentAnalyses") ?? "[]")).toEqual([
      "analysis-ok",
    ]);
    expect(pushMock).not.toHaveBeenCalled();
  });

  it("prevents duplicate submissions while an upload is pending", async () => {
    const user = userEvent.setup();
    const file = new File(["video"], "match.mp4", { type: "video/mp4" });
    const onUploadComplete = vi.fn();
    let resolveUpload!: (job: AnalysisJob) => void;
    const uploadAnalysis = vi.fn<UploadAnalysisFn>(
      () =>
        new Promise((resolve) => {
          resolveUpload = resolve;
        }),
    );

    renderWithQueryClient(
      <UploadDropzone
        uploadAnalysis={uploadAnalysis}
        onUploadComplete={onUploadComplete}
      />,
    );

    await user.upload(screen.getByLabelText("Match video file"), file);
    await user.click(screen.getByRole("button", { name: /upload selected video/i }));
    await waitFor(() => expect(screen.getByRole("button", { name: /uploading/i })).toBeDisabled());
    await user.click(screen.getByRole("button", { name: /uploading/i }));

    expect(uploadAnalysis).toHaveBeenCalledTimes(1);
    resolveUpload(makeJob({ analysis_id: "analysis-pending" }));
    await waitFor(() => expect(onUploadComplete).toHaveBeenCalledTimes(1));
  });
});
