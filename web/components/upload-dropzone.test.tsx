import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { UploadDropzone, type UploadAnalysisFn } from "@/components/upload-dropzone";
import type { DuplicateUploadResponse, UploadAnalysisResponse } from "@/lib/api/types";
import { makeJob } from "@/test/factories";
import { renderWithQueryClient } from "@/test/render";

const pushMock = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({
  usePathname: () => "/upload-match",
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

    await waitFor(() =>
      expect(uploadAnalysis).toHaveBeenCalledWith(
        file,
        expect.any(Function),
        expect.objectContaining({
          idempotencyKey: expect.any(String),
          reanalyze: false,
        }),
      ),
    );
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
    let resolveUpload!: (job: UploadAnalysisResponse) => void;
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

  it("shows the exact-duplicate decision and Cancel returns to upload", async () => {
    const user = userEvent.setup();
    const file = new File(["video"], "match.mp4", { type: "video/mp4" });
    const uploadAnalysis = vi.fn<UploadAnalysisFn>().mockResolvedValue(makeDuplicate());

    renderWithQueryClient(<UploadDropzone uploadAnalysis={uploadAnalysis} />);

    await user.upload(screen.getByLabelText("Match video file"), file);
    await user.click(screen.getByRole("button", { name: /upload selected video/i }));

    const dialog = await screen.findByRole("dialog", {
      name: "This video has already been uploaded.",
    });
    expect(dialog).toHaveTextContent(/You analyzed this video on/i);
    expect(screen.getByRole("button", { name: "Open Existing Analysis" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Analyze Again" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /upload selected video/i })).toBeInTheDocument();
  });

  it("opens the existing owner-scoped analysis from the duplicate decision", async () => {
    const user = userEvent.setup();
    const file = new File(["video"], "renamed.mp4", { type: "video/mp4" });
    const uploadAnalysis = vi.fn<UploadAnalysisFn>().mockResolvedValue(makeDuplicate());

    renderWithQueryClient(<UploadDropzone uploadAnalysis={uploadAnalysis} />);

    await user.upload(screen.getByLabelText("Match video file"), file);
    await user.click(screen.getByRole("button", { name: /upload selected video/i }));
    await user.click(
      await screen.findByRole("button", { name: "Open Existing Analysis" }),
    );

    expect(pushMock).toHaveBeenCalledWith("/matches/existing-analysis");
  });

  it("uses a new idempotency key when the user chooses Analyze Again", async () => {
    const user = userEvent.setup();
    const file = new File(["video"], "match.mp4", { type: "video/mp4" });
    const onUploadComplete = vi.fn();
    const uploadAnalysis = vi
      .fn<UploadAnalysisFn>()
      .mockResolvedValueOnce(makeDuplicate())
      .mockResolvedValueOnce(makeJob({ analysis_id: "reanalyzed" }));

    renderWithQueryClient(
      <UploadDropzone
        uploadAnalysis={uploadAnalysis}
        onUploadComplete={onUploadComplete}
      />,
    );

    await user.upload(screen.getByLabelText("Match video file"), file);
    await user.click(screen.getByRole("button", { name: /upload selected video/i }));
    await user.click(await screen.findByRole("button", { name: "Analyze Again" }));

    await waitFor(() => expect(onUploadComplete).toHaveBeenCalledTimes(1));
    expect(uploadAnalysis).toHaveBeenCalledTimes(2);
    const firstOptions = uploadAnalysis.mock.calls[0][2];
    const reanalyzeOptions = uploadAnalysis.mock.calls[1][2];
    expect(reanalyzeOptions).toMatchObject({ reanalyze: true });
    expect(reanalyzeOptions?.idempotencyKey).not.toBe(firstOptions?.idempotencyKey);
  });

  it("reuses the upload idempotency key when a failed request is retried", async () => {
    const user = userEvent.setup();
    const file = new File(["video"], "match.mp4", { type: "video/mp4" });
    const onUploadComplete = vi.fn();
    const uploadAnalysis = vi
      .fn<UploadAnalysisFn>()
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(makeJob({ analysis_id: "retried" }));

    renderWithQueryClient(
      <UploadDropzone
        uploadAnalysis={uploadAnalysis}
        onUploadComplete={onUploadComplete}
      />,
    );

    await user.upload(screen.getByLabelText("Match video file"), file);
    await user.click(screen.getByRole("button", { name: /upload selected video/i }));
    expect(await screen.findByText("Court4 backend is unavailable.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /upload selected video/i }));

    await waitFor(() => expect(onUploadComplete).toHaveBeenCalledTimes(1));
    const firstKey = uploadAnalysis.mock.calls[0][2]?.idempotencyKey;
    const retryKey = uploadAnalysis.mock.calls[1][2]?.idempotencyKey;
    expect(retryKey).toBe(firstKey);
  });
});

function makeDuplicate(): DuplicateUploadResponse {
  return {
    status: "duplicate",
    duplicate_type: "exact",
    existing_analysis_id: "existing-analysis",
    uploaded_at: "2026-07-30T12:00:00Z",
    actions: {
      open_existing: true,
      reanalyze: true,
    },
  };
}
