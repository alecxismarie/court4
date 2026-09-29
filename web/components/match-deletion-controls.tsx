"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button, ButtonLink } from "@/components/ui/button";
import { ConfirmationDialog } from "@/components/confirmation-dialog";
import { deleteMatch, getMatchLifecycle } from "@/lib/api/source-media";
import { normalizeApiError } from "@/lib/api/client";

export function MatchDeletionControls({ analysisId, state = "live" }: {
  analysisId: string; state?: "live" | "deletion_pending" | "deleted";
}) {
  const [confirming, setConfirming] = useState(false);
  const client = useQueryClient();
  const mutation = useMutation({
    mutationFn: () => deleteMatch(analysisId),
    onSuccess: () => setConfirming(false),
    onSettled: async (_data, error) => {
      // Even a failed purge may have accepted deletion and retired this match.
      const lifecycle = error
        ? await getMatchLifecycle(analysisId).catch(() => null)
        : { analysis_id: analysisId, state: "deleted" as const };
      if (lifecycle) client.setQueryData(["match-lifecycle", analysisId], lifecycle);
      if (!lifecycle || lifecycle.state !== "live") {
        client.removeQueries({ queryKey: ["analysis", analysisId] });
        await Promise.all([
          client.invalidateQueries({ queryKey: ["analysis-history"] }),
          client.invalidateQueries({ queryKey: ["play-history"] }),
        ]);
      }
    },
  });
  if (state === "deleted" || mutation.isSuccess) return <MatchDeletedState />;
  return <section className="space-y-3 rounded-md border border-red-200 bg-white p-5">
    <h2 className="font-semibold">Delete match &amp; analysis</h2>
    <p>Permanently removes this match and its analysis from Court4. It will be removed from History and will no longer contribute to Progress.</p>
    {state === "deletion_pending" ? <p role="status">Deletion is unfinished. This match is already excluded from History and Progress. Retry to finish removing its saved data.</p> : null}
    <Button variant="destructive" onClick={() => setConfirming(true)}>{state === "deletion_pending" ? "Retry match deletion" : "Delete match & analysis"}</Button>
    {confirming ? <ConfirmationDialog title="Delete match & analysis permanently?" busy={mutation.isPending} onClose={() => setConfirming(false)}>
      <p className="mt-3">The recording, derived media, and analysis results will be removed. This cannot be undone. Your Progress will be recalculated from your remaining matches.</p>
      {mutation.isError ? <p role="alert" className="mt-3 text-court-red">{normalizeApiError(mutation.error).message}</p> : null}
      <div className="mt-5 flex flex-wrap gap-3">
        <Button variant="secondary" disabled={mutation.isPending} onClick={() => setConfirming(false)}>Cancel</Button>
        <Button variant="destructive" disabled={mutation.isPending} onClick={() => mutation.mutate()}>{mutation.isPending ? "Deleting match…" : "Permanently delete match & analysis"}</Button>
      </div>
    </ConfirmationDialog> : null}
  </section>;
}

function MatchDeletedState() {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    // Run after the confirmation dialog restores focus to its former trigger.
    const frame = requestAnimationFrame(() => {
      heading.current?.focus({ preventScroll: true });
      window.scrollTo({ top: 0, behavior: "instant" });
    });
    return () => cancelAnimationFrame(frame);
  }, []);

  return <section aria-labelledby="match-deleted-heading" className="space-y-5 rounded-md border border-court-line bg-white p-6 shadow-panel">
    <h1 id="match-deleted-heading" ref={heading} tabIndex={-1} className="text-2xl font-semibold text-court-ink">
      Match and analysis deleted
    </h1>
    <p role="status" className="text-court-muted">
      Your match, recording and analysis have been deleted. This match was removed from History and no longer contributes to Progress.
    </p>
    <div className="flex flex-wrap gap-3">
      <ButtonLink href="/upload-match">Upload another match</ButtonLink>
      <ButtonLink href="/analysis-history" variant="secondary">Back to History</ButtonLink>
    </div>
  </section>;
}
