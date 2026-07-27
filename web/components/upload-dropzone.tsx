"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FileVideo2, RotateCcw, Upload } from "lucide-react";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { createAnalysis } from "@/lib/api/analyses";
import { normalizeApiError } from "@/lib/api/client";
import type { AnalysisJob, UploadProgress as UploadProgressValue } from "@/lib/api/types";
import { getPublicEnv } from "@/lib/env";
import { rememberAnalysisId } from "@/lib/recent-analyses";
import { cn, formatFileSize } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { UploadProgress } from "@/components/upload-progress";

type UploadFormValues = {
  file: File;
};

export type UploadAnalysisFn = (
  file: File,
  onProgress?: (progress: UploadProgressValue) => void,
) => Promise<AnalysisJob>;

export function UploadDropzone({
  uploadAnalysis = createAnalysis,
  onUploadComplete,
}: {
  uploadAnalysis?: UploadAnalysisFn;
  onUploadComplete?: (job: AnalysisJob) => void;
}) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const inputRef = useRef<HTMLInputElement | null>(null);
  const publicEnv = getPublicEnv();
  const [progress, setProgress] = useState<UploadProgressValue | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);

  const form = useForm<UploadFormValues>({
    resolver: zodResolver(buildUploadSchema(publicEnv)),
  });
  const selectedFile = form.watch("file");

  const uploadMutation = useMutation({
    mutationFn: (file: File) => uploadAnalysis(file, setProgress),
    onMutate: () => {
      setApiError(null);
      setProgress({ loaded: 0, total: selectedFile?.size ?? null, percent: 0 });
    },
    onSuccess: (job) => {
      rememberAnalysisId(job.analysis_id);
      void queryClient.invalidateQueries({ queryKey: ["analysis"] });
      void queryClient.invalidateQueries({ queryKey: ["recent-analyses"] });
      if (onUploadComplete) {
        onUploadComplete(job);
        return;
      }
      router.push(`/matches/${job.analysis_id}`);
    },
    onError: (error) => {
      const normalized = normalizeApiError(error);
      setApiError(normalized.message);
    },
  });

  const chooseFile = (file: File | null) => {
    if (!file || uploadMutation.isPending) {
      return;
    }
    form.setValue("file", file, { shouldDirty: true, shouldValidate: true });
    setApiError(null);
    setProgress(null);
  };

  const submit = form.handleSubmit((values) => {
    if (uploadMutation.isPending) {
      return;
    }
    uploadMutation.mutate(values.file);
  });

  const reset = () => {
    if (uploadMutation.isPending) {
      return;
    }
    form.reset();
    setProgress(null);
    setApiError(null);
    if (inputRef.current) {
      inputRef.current.value = "";
    }
  };

  const errorMessage = form.formState.errors.file?.message ?? apiError;

  return (
    <form onSubmit={submit} className="space-y-5" aria-label="Upload match video">
      <section className="rounded-md border border-court-line bg-court-panel p-5">
        <h2 className="text-lg font-semibold text-court-ink">
          How to make a clear Court4 video
        </h2>
        <ul className="mt-3 grid list-disc gap-2 pl-5 text-sm text-court-muted md:grid-cols-2">
          <li>Place the camera behind or diagonally behind the baseline.</li>
          <li>Keep the full court visible.</li>
          <li>Use landscape orientation when possible.</li>
          <li>Keep the camera stable.</li>
          <li>Record at 720p minimum; 1080p is recommended.</li>
          <li>Capture enough continuous gameplay.</li>
          <li>Usable tracked time matters more than total duration.</li>
        </ul>
      </section>

      <div
        role="button"
        tabIndex={0}
        aria-label="Choose or drop a match video"
        onClick={() => inputRef.current?.click()}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            inputRef.current?.click();
          }
        }}
        onDragOver={(event) => {
          event.preventDefault();
        }}
        onDrop={(event) => {
          event.preventDefault();
          chooseFile(event.dataTransfer.files.item(0));
        }}
        className={cn(
          "rounded-md border-2 border-dashed bg-white p-8 text-center transition",
          errorMessage ? "border-court-red" : "border-court-line hover:border-court-green",
          uploadMutation.isPending && "pointer-events-none opacity-70",
        )}
      >
        <input
          ref={inputRef}
          type="file"
          className="sr-only"
          accept={publicEnv.supportedVideoExtensions.join(",")}
          aria-label="Match video file"
          onChange={(event) => chooseFile(event.target.files?.item(0) ?? null)}
        />
        <div className="mx-auto grid h-14 w-14 place-items-center rounded-md bg-court-panel text-court-green">
          <FileVideo2 aria-hidden="true" className="h-7 w-7" />
        </div>
        <h2 className="mt-5 text-xl font-semibold text-court-ink">Upload a match video</h2>
        <p className="mx-auto mt-2 max-w-2xl text-sm leading-6 text-court-muted">
          Court4 currently processes one pickleball match video at a time. After upload,
          you will confirm the court view and choose which tracked player is you.
        </p>
        <p className="mt-4 text-sm font-medium text-court-blue">
          Drag a video here or press Enter to choose a file.
        </p>
      </div>

      {selectedFile ? (
        <div className="rounded-md border border-court-line bg-white p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-court-ink">{selectedFile.name}</p>
              <p className="text-sm text-court-muted">{formatFileSize(selectedFile.size)}</p>
            </div>
            <Button type="button" variant="secondary" onClick={reset} disabled={uploadMutation.isPending}>
              <RotateCcw aria-hidden="true" className="h-4 w-4" />
              Reset
            </Button>
          </div>
        </div>
      ) : null}

      {errorMessage ? (
        <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-court-red">
          {errorMessage}
        </div>
      ) : null}

      {progress ? <UploadProgress progress={progress} /> : null}

      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" disabled={!selectedFile || uploadMutation.isPending}>
          <Upload aria-hidden="true" className="h-4 w-4" />
          {uploadMutation.isPending ? "Uploading" : "Upload selected video"}
        </Button>
        <p className="text-sm text-court-muted">
          Accepted formats: {publicEnv.supportedVideoExtensions.join(", ")}. Maximum size:{" "}
          {formatFileSize(publicEnv.maxUploadBytes)}.
        </p>
      </div>
    </form>
  );
}

function buildUploadSchema(env: ReturnType<typeof getPublicEnv>) {
  return z.object({
    file: z
      .custom<File>((value): value is File => value instanceof File, {
        message: "Select a match video to upload.",
      })
      .refine((file) => file.size > 0, "Selected file is empty.")
      .refine((file) => file.size <= env.maxUploadBytes, "Selected video is too large.")
      .refine((file) => {
        const extension = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
        return env.supportedVideoExtensions.includes(extension);
      }, "Court4 supports .mp4, .mov, .avi, and .mkv videos."),
  });
}
