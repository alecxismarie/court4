"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { AuthenticatedImage } from "@/components/authenticated-image";
import { Button, ButtonLink } from "@/components/ui/button";
import { confirmCalibration } from "@/lib/api/analyses";
import { getArtifactUrl, normalizeApiError } from "@/lib/api/client";
import type { AnalysisJob } from "@/lib/api/types";

export function CalibrationReview({ job }: { job: AnalysisJob }) {
  const cache = useQueryClient();
  const [overlayLoaded, setOverlayLoaded] = useState(false);
  const confirmation = useMutation({
    mutationFn: () => confirmCalibration(job.analysis_id, job.active_calibration_id!, job.calibration_checksum_sha256!),
    onSuccess: async (saved) => {
      cache.setQueryData(["analysis", job.analysis_id], saved);
      await cache.invalidateQueries({ queryKey: ["analysis", job.analysis_id] });
      await cache.invalidateQueries({ queryKey: ["analysis-history"] });
      await cache.invalidateQueries({ queryKey: ["play-history"] });
    },
  });
  const verified = job.calibration_verified || confirmation.data?.calibration_verified;
  return (
    <section className="space-y-4 rounded-md border border-court-line bg-white p-5" aria-label="Review court calibration">
      <h3 className="text-lg font-semibold">{verified ? "Court verified for measurements" : "Check the court overlay"}</h3>
      <p>Check that the outer corners, sidelines, baselines, and kitchen lines follow the playable floor. Near and far must match the camera view. Recognition confidence scores the proposed shape; it does not verify floor alignment.</p>
      {job.active_calibration_id ? (
        <AuthenticatedImage
          src={getArtifactUrl(job.analysis_id, `calibrations/${job.active_calibration_id}/verification.jpg`)}
          alt="Court calibration overlay for review"
          className="block h-auto w-full rounded-md"
          onLoad={() => setOverlayLoaded(true)}
          onError={() => setOverlayLoaded(false)}
        />
      ) : <p>The current court could not be identified. Adjust the court to create a new proposal.</p>}
      {confirmation.isError ? <p role="alert">{normalizeApiError(confirmation.error).message}</p> : null}
      <div className="flex flex-wrap gap-3">
        {!verified ? <Button onClick={() => confirmation.mutate()} disabled={!overlayLoaded || !job.active_calibration_id || !job.calibration_checksum_sha256 || confirmation.isPending}>
          {confirmation.isPending ? "Saving confirmation" : "Looks correct"}
        </Button> : null}
        <ButtonLink href={`/matches/${job.analysis_id}/calibrate`} variant="secondary">Adjust court</ButtonLink>
      </div>
      {!verified ? <p>Player positioning and movement measurements stay unavailable until you confirm this court.</p> : null}
    </section>
  );
}
