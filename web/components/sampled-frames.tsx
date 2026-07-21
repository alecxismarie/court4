"use client";

import { ImageOff } from "lucide-react";
import { useState } from "react";

import { getArtifactUrl } from "@/lib/api/client";
import type { SampledFrame } from "@/lib/api/types";
import { formatFileSize } from "@/lib/utils";
import { EmptyState } from "@/components/empty-state";
import { Skeleton } from "@/components/skeleton";

export function SampledFrames({
  analysisId,
  frames,
  isLoading,
}: {
  analysisId: string;
  frames: SampledFrame[];
  isLoading: boolean;
}) {
  if (isLoading) {
    return (
      <section className="rounded-md border border-court-line bg-white p-5 shadow-panel">
        <h2 className="text-lg font-semibold text-court-ink">Sampled frames</h2>
        <div className="mt-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {[1, 2, 3].map((key) => (
            <Skeleton key={key} className="aspect-video" />
          ))}
        </div>
      </section>
    );
  }

  if (frames.length === 0) {
    return (
      <EmptyState
        title="No sampled frames yet"
        description="Court4 will show inspection frames here after the uploaded video has been inspected."
      />
    );
  }

  return (
    <section className="rounded-md border border-court-line bg-white p-5 shadow-panel">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-court-ink">Sampled frames</h2>
          <p className="text-sm text-court-muted">
            Use these frames to pick the clearest court view before calibration.
          </p>
        </div>
        <span className="text-sm font-medium text-court-muted">{frames.length} frame(s)</span>
      </div>
      <div className="mt-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {frames.map((frame) => (
          <SampledFrameCard key={frame.path} analysisId={analysisId} frame={frame} />
        ))}
      </div>
    </section>
  );
}

function SampledFrameCard({ analysisId, frame }: { analysisId: string; frame: SampledFrame }) {
  const [broken, setBroken] = useState(false);
  const filename = frame.path.split("/").at(-1) ?? frame.path;

  return (
    <article className="overflow-hidden rounded-md border border-court-line bg-court-panel">
      <div className="aspect-video bg-white">
        {broken ? (
          <div className="grid h-full place-items-center text-court-muted">
            <span className="flex items-center gap-2 text-sm">
              <ImageOff aria-hidden="true" className="h-5 w-5" />
              Frame unavailable
            </span>
          </div>
        ) : (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={getArtifactUrl(analysisId, frame.path)}
            alt={`Sampled frame ${frame.frame_number}`}
            className="h-full w-full object-cover"
            onError={() => setBroken(true)}
          />
        )}
      </div>
      <div className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
        <span className="font-medium text-court-ink">{filename}</span>
        <span className="text-court-muted">{formatFileSize(frame.size_bytes)}</span>
      </div>
    </article>
  );
}
