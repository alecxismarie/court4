"use client";

import { BarChart3, Upload } from "lucide-react";

import { useWorkspaceAnalyses } from "@/lib/use-workspace-analyses";
import {
  formatDistanceFeet,
  formatTrackedTime,
} from "@/lib/workspace-data";
import { formatDateTime } from "@/lib/utils";
import { EmptyState } from "@/components/empty-state";
import { ButtonLink } from "@/components/ui/button";

export function PerformanceWorkspace() {
  const { summary, isLoading, analysisIds } = useWorkspaceAnalyses();
  const recentMatchIq = summary.completedMatches
    .filter((record) => record.analytics?.match_iq?.status === "generated")
    .slice(0, 3);

  return (
    <div className="space-y-6">
      <section className="rounded-md border border-court-line bg-white p-6 shadow-panel">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-sm font-semibold uppercase tracking-wide text-court-green">
              Performance
            </p>
            <h1 className="mt-2 text-3xl font-semibold text-court-ink">
              Current performance snapshot
            </h1>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-court-muted">
              Factual totals from your completed Court4 match analyses.
            </p>
          </div>
          <ButtonLink href="/matches/upload">
            <Upload aria-hidden="true" className="h-4 w-4" />
            Upload Match
          </ButtonLink>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <SnapshotCard label="Matches analyzed" value={String(summary.completedMatchCount)} />
        <SnapshotCard
          label="Cumulative distance"
          value={formatDistanceFeet(summary.totalDistanceFeet)}
        />
        <SnapshotCard
          label="Cumulative tracked time"
          value={formatTrackedTime(summary.totalTrackedSeconds)}
        />
        <SnapshotCard
          label="Most common measured zone"
          value={
            summary.mostCommonZone
              ? `${summary.mostCommonZone.label} ${formatTrackedTime(summary.mostCommonZone.seconds ?? null)}`
              : "Unavailable"
          }
        />
      </section>

      <section className="rounded-md border border-court-line bg-white p-5 shadow-panel">
        <h2 className="text-xl font-semibold text-court-ink">Recent Match IQ summaries</h2>
        {isLoading && analysisIds.length > 0 ? (
          <p className="mt-3 text-sm text-court-muted">Loading performance facts.</p>
        ) : recentMatchIq.length ? (
          <div className="mt-4 grid gap-3">
            {recentMatchIq.map((record) => (
              <article
                key={record.analysisId}
                className="rounded-md border border-court-line bg-court-panel p-4"
              >
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <h3 className="font-semibold text-court-ink">
                    {record.analytics?.match_iq?.quality_gate === "NORMAL"
                      ? "Verified movement insight"
                      : record.analytics?.match_iq?.quality_gate === "CAUTIOUS"
                        ? "Analysis under review"
                        : "Limited by recording quality"}
                  </h3>
                  <span className="text-sm text-court-muted">
                    {record.analytics
                      ? formatDateTime(record.analytics.analytics.created_at)
                      : "Date unavailable"}
                  </span>
                </div>
                <p className="mt-2 text-sm leading-6 text-court-muted">
                  {record.analytics?.match_iq?.summary}
                </p>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState
            className="mt-4"
            title="No completed Match IQ reports yet"
            description="Performance facts will appear after Court4 generates Match IQ for a match."
            action={<ButtonLink href="/matches/upload">Upload Match</ButtonLink>}
          />
        )}
      </section>

      <section className="rounded-md border border-court-line bg-white p-5 shadow-panel">
        <div className="flex gap-3">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-md bg-court-panel text-court-green">
            <BarChart3 aria-hidden="true" className="h-5 w-5" />
          </span>
          <div>
            <h2 className="text-xl font-semibold text-court-ink">Future progress</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-court-muted">
              Progress trends will appear here after Court4 has enough match history to
              compare your sessions reliably.
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}

function SnapshotCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-court-line bg-white p-4 shadow-panel">
      <dt className="text-xs font-semibold uppercase tracking-wide text-court-muted">{label}</dt>
      <dd className="mt-2 break-words text-2xl font-semibold text-court-ink">{value}</dd>
    </div>
  );
}
