import { Upload } from "lucide-react";

import { RecentMatches } from "@/components/recent-matches";
import { ButtonLink } from "@/components/ui/button";

export default function MatchesPage() {
  return (
    <div className="space-y-6">
      <section className="rounded-md border border-court-line bg-white p-6 shadow-panel">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-sm font-semibold uppercase tracking-wide text-court-green">
              Matches
            </p>
            <h1 className="mt-2 text-3xl font-semibold text-court-ink">Recent analyses</h1>
            <p className="mt-2 text-sm text-court-muted">
              This list is remembered locally in your browser after successful uploads.
            </p>
          </div>
          <ButtonLink href="/matches/upload">
            <Upload aria-hidden="true" className="h-4 w-4" />
            Upload Match
          </ButtonLink>
        </div>
      </section>
      <RecentMatches />
    </div>
  );
}
