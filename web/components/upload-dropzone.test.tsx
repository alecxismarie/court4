import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { UploadDropzone, type UploadAnalysisFn } from "@/components/upload-dropzone";
import { TerminalUploadError } from "@/lib/api/analyses";
import type { DuplicateUploadResponse, UploadAnalysisResponse } from "@/lib/api/types";
import { makeJob } from "@/test/factories";
import { renderWithQueryClient } from "@/test/render";

const pushMock = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({
  usePathname: () => "/upload-match",
  useRouter: () => ({ push: pushMock }),
}));

describe("upload dropzone", () => {
  afterEach(() => vi.restoreAllMocks());
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
    expect(screen.getByText("Supported")).toBeInTheDocument();
    expect(screen.getByText("Experimental")).toBeInTheDocument();
  });

  it("submits the selected Padel sport through the experimental path", async () => {
    const user = userEvent.setup();
    const file = new File(["video"], "padel.mp4", { type: "video/mp4" });
    const uploadAnalysis = vi
      .fn<UploadAnalysisFn>()
      .mockResolvedValue(makeJob({ analysis_id: "padel-analysis", sport: "padel" }));

    renderWithQueryClient(<UploadDropzone uploadAnalysis={uploadAnalysis} onUploadComplete={vi.fn()} />);
    await user.click(screen.getByRole("radio", { name: /Padel/i }));
    await user.upload(screen.getByLabelText("Match video file"), file);
    await user.click(screen.getByRole("button", { name: /upload selected video/i }));

    await waitFor(() =>
      expect(uploadAnalysis).toHaveBeenCalledWith(
        file,
        expect.any(Function),
        expect.objectContaining({ sport: "padel" }),
      ),
    );
    expect(screen.getByText(/will not run Pickleball court logic or Match IQ/i)).toBeInTheDocument();
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
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /upload selected video/i }));

    await waitFor(() => expect(onUploadComplete).toHaveBeenCalledTimes(1));
    const firstKey = uploadAnalysis.mock.calls[0][2]?.idempotencyKey;
    const retryKey = uploadAnalysis.mock.calls[1][2]?.idempotencyKey;
    expect(retryKey).toBe(firstKey);
  });

  it("uses a fresh key after confirmed terminal cleanup", async () => {
    const user = userEvent.setup();
    const uploadAnalysis = vi.fn<UploadAnalysisFn>()
      .mockRejectedValueOnce(new TerminalUploadError("Upload was canceled.", {
        code: "upload_canceled",
      }))
      .mockResolvedValueOnce(makeJob());
    renderWithQueryClient(<UploadDropzone uploadAnalysis={uploadAnalysis} />);
    await user.upload(screen.getByLabelText("Match video file"), new File(["video"], "match.mp4"));
    await user.click(screen.getByRole("button", { name: /upload selected video/i }));
    await screen.findByText("Upload was canceled.");
    await user.click(screen.getByRole("button", { name: /upload selected video/i }));
    await waitFor(() => expect(uploadAnalysis).toHaveBeenCalledTimes(2));
    expect(uploadAnalysis.mock.calls[1][2]?.idempotencyKey)
      .not.toBe(uploadAnalysis.mock.calls[0][2]?.idempotencyKey);
  });

  it("Cancel upload signals cancellation and Reset clears the settled form", async () => {
    const user = userEvent.setup();
    const uploadAnalysis = vi.fn<UploadAnalysisFn>((_file, _progress, options) =>
      new Promise((_resolve, reject) => {
        options?.signal?.addEventListener("abort", () => reject(
          new TerminalUploadError("Upload was canceled.", { code: "upload_canceled" }),
        ));
      }),
    );
    renderWithQueryClient(<UploadDropzone uploadAnalysis={uploadAnalysis} />);
    await user.upload(screen.getByLabelText("Match video file"), new File(["video"], "match.mp4"));
    await user.click(screen.getByRole("button", { name: /upload selected video/i }));
    await user.click(await screen.findByRole("button", { name: "Cancel upload" }));
    await screen.findByText("Upload was canceled.");
    expect(uploadAnalysis.mock.calls[0][2]?.signal?.aborted).toBe(true);
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reset" }));
    expect(screen.queryByText("match.mp4")).not.toBeInTheDocument();
  });

  it.each(["reset", "replacement"])("%s retries abort of a known session", async (action) => {
    const user = userEvent.setup();
    const id = "8b2ee1d1-3176-4a9e-a643-66559d667e47";
    const uploadAnalysis = vi.fn<UploadAnalysisFn>(async (_file, _progress, options) => {
      options?.onSession?.(id);
      throw new TypeError("offline");
    });
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(
      JSON.stringify({ status: "aborted" }), { status: 200 },
    ));
    renderWithQueryClient(<UploadDropzone uploadAnalysis={uploadAnalysis} />);
    await user.upload(screen.getByLabelText("Match video file"), new File(["video"], "match.mp4"));
    await user.click(screen.getByRole("button", { name: /upload selected video/i }));
    await screen.findByText("Court4 backend is unavailable.");
    if (action === "reset") {
      await user.click(screen.getByRole("button", { name: "Reset" }));
    } else {
      await user.upload(screen.getByLabelText("Match video file"), new File(["new"], "new.mov"));
      await screen.findByText("new.mov");
    }
    await waitFor(() => expect(screen.queryByText("match.mp4")).not.toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledWith(
      `http://localhost:8000/api/v1/uploads/${id}`, expect.objectContaining({ method: "DELETE" }),
    );
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
