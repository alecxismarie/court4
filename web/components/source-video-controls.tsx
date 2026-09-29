"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { ConfirmationDialog } from "@/components/confirmation-dialog";
import { deleteSourceVideo } from "@/lib/api/source-media";
import { normalizeApiError } from "@/lib/api/client";
import type { AnalysisJob } from "@/lib/api/types";

export function SourceVideoControls({ job }: { job: AnalysisJob }) {
  const [confirming, setConfirming] = useState(false);
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: () => deleteSourceVideo(job.analysis_id),
    onSuccess: () => {
      queryClient.setQueryData(["analysis", job.analysis_id], {
        ...job,
        source_media_state: "deleted",
        available_artifacts: job.available_artifacts.filter((item) => item.path !== job.source_video && !item.content_type.startsWith("video/")),
      });
      setConfirming(false);
    },
  });
  if (job.source_media_state === "deleted" || mutation.isSuccess) {
    return (
      <p role="status" className="text-sm text-court-muted">
        Source video deleted, including large playback videos. Your analysis, Match IQ, History and Progress remain available. Reanalysis from the original video is no longer available.
      </p>
    );
  }
  const eligible =
    (job.status === "completed" && job.analytics_completed) ||
    (job.sport === "padel" && job.inspection_completed);
  if (!eligible || !job.source_video || job.source_media_state === "unavailable") return null;
  return (
    <section className="rounded-md border border-court-line bg-white p-5">
      {job.source_media_state === "deleting" ? (
        <p className="mb-3 text-sm text-court-muted">
          Video deletion is unfinished. Retry to complete it. Your analysis and Progress history remain available.
        </p>
      ) : null}
      {(
        <Button type="button" variant="secondary" onClick={() => setConfirming(true)}>
          Delete original video
        </Button>
      )}
      {confirming ? (
        <ConfirmationDialog title="Delete original video?" busy={mutation.isPending} onClose={() => setConfirming(false)}>
          <p className="mt-2 text-sm text-court-muted">
            The original recording and large derived playback videos will be permanently removed to free storage.
            Your completed analysis, Match IQ, Analysis History and Progress history will remain, but Court4 will
            no longer be able to reanalyze this match from the original video.
          </p>
          {mutation.isError ? (
            <p role="alert" className="mt-3 text-sm text-court-red">
              {normalizeApiError(mutation.error).message}
            </p>
          ) : null}
          <div className="mt-4 flex gap-3">
            <Button type="button" variant="secondary" disabled={mutation.isPending} onClick={() => setConfirming(false)}>
              Keep video
            </Button>
            <Button type="button" disabled={mutation.isPending} onClick={() => mutation.mutate()}>
              {mutation.isPending ? "Deleting video…" : "Permanently delete video"}
            </Button>
          </div>
        </ConfirmationDialog>
      ) : null}
    </section>
  );
}
