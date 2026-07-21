import { ArrowLeft, Crosshair } from "lucide-react";

import { ButtonLink } from "@/components/ui/button";

export default function CalibrationPlaceholderPage({
  params,
}: {
  params: { analysisId: string };
}) {
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <section className="rounded-md border border-court-line bg-white p-6 shadow-panel">
        <span className="grid h-12 w-12 place-items-center rounded-md bg-court-panel text-court-green">
          <Crosshair aria-hidden="true" className="h-6 w-6" />
        </span>
        <p className="mt-5 text-sm font-semibold uppercase tracking-wide text-court-green">
          Phase 1.0B
        </p>
        <h1 className="mt-2 text-3xl font-semibold text-court-ink">
          Interactive court calibration is next
        </h1>
        <p className="mt-3 text-sm leading-6 text-court-muted">
          This placeholder is reserved for marking near-left, near-right, far-right, and far-left
          court corners on a sampled frame. No calibration is submitted from this page yet.
        </p>
        <div className="mt-6">
          <ButtonLink href={`/matches/${params.analysisId}`} variant="secondary">
            <ArrowLeft aria-hidden="true" className="h-4 w-4" />
            Back to Match
          </ButtonLink>
        </div>
      </section>
    </div>
  );
}
