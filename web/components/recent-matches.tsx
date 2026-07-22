"use client";

import { BarChart3, ExternalLink, RefreshCw, Share2 } from "lucide-react";
import Link from "next/link";

import { useWorkspaceAnalyses } from "@/lib/use-workspace-analyses";
import {
  formatDistanceFeet,
  getDominantZone,
  getHumanMatchStatus,
  getMatchIqAvailability,
  hasGeneratedMatchIq,
  type WorkspaceAnalysisRecord,
} from "@/lib/workspace-data";
import { cn, formatDateTime, shortenAnalysisId } from "@/lib/utils";
import { EmptyState } from "@/components/empty-state";
import { ButtonLink } from "@/components/ui/button";

export function RecentMatches({
  compact = false,
  limit,
  showHeading = true,
}: {
  compact?: boolean;
  limit?: number;
  showHeading?: boolean;
}) {
  const { analysisIds, records, isLoading } = useWorkspaceAnalyses();
  const visibleRecords = typeof limit === "number" ? records.slice(0, limit) : records;

  if (analysisIds.length === 0) {
    return (
      <EmptyState
        title="No recent matches"
        description="Your analyzed matches will be remembered locally in this browser."
        action={<ButtonLink href="/matches/upload">Upload Match</ButtonLink>}
      />
    );
  }

  return (
    <section className="rounded-md border border-court-line bg-white shadow-panel">
      {showHeading ? (
        <div className="border-b border-court-line px-5 py-4">
          <h2 className="text-lg font-semibold text-court-ink">Recent matches</h2>
          <p className="text-sm text-court-muted">Stored locally in this browser.</p>
        </div>
      ) : null}
      <div className="divide-y divide-court-line">
        {visibleRecords.map((record) => (
          <RecentMatchRow key={record.analysisId} record={record} compact={compact} />
        ))}
        {isLoading && visibleRecords.length === 0 ? (
          <div className="px-5 py-4 text-sm text-court-muted">Loading recent matches.</div>
        ) : null}
      </div>
    </section>
  );
}

function RecentMatchRow({
  record,
  compact,
}: {
  record: WorkspaceAnalysisRecord;
  compact: boolean;
}) {
  if (!record.job) {
    const message = record.jobError ?? "Match details are loading.";
    return (
      <article className="flex flex-wrap items-center justify-between gap-3 px-5 py-4">
        <div>
          <p className="font-medium text-court-ink">{shortenAnalysisId(record.analysisId)}</p>
          <p className="text-sm text-court-muted">{message}</p>
        </div>
        <span className="inline-flex items-center gap-2 rounded-md border border-court-line px-3 py-2 text-sm font-semibold text-court-muted">
          <RefreshCw aria-hidden="true" className="h-4 w-4" />
          Loading
        </span>
      </article>
    );
  }

  const analytics = record.analytics?.analytics ?? null;
  const dominantZone = getDominantZone(record);
  const matchIqReady = hasGeneratedMatchIq(record);
  const matchIqAvailability = getMatchIqAvailability(record);
  const canShare = matchIqReady && Boolean(analytics);

  return (
    <article className="grid gap-4 px-5 py-4 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="break-all font-semibold text-court-ink">
            {shortenAnalysisId(record.job.analysis_id)}
          </h3>
          <span className="rounded-md bg-court-panel px-2 py-1 text-xs font-semibold text-court-muted">
            {getHumanMatchStatus(record.job)}
          </span>
          <span
            className={cn(
              "rounded-md px-2 py-1 text-xs font-semibold",
              matchIqReady
                ? "bg-green-50 text-court-green"
                : "bg-court-panel text-court-muted",
            )}
          >
            {matchIqAvailability}
          </span>
        </div>
        <dl className="mt-2 grid gap-2 text-sm text-court-muted sm:grid-cols-3">
          <MatchFact label="Date" value={formatDateTime(record.job.created_at)} />
          <MatchFact
            label="Distance"
            value={analytics ? formatDistanceFeet(analytics.distance.total_distance_feet) : "Unavailable"}
          />
          <MatchFact
            label="Court position"
            value={
              dominantZone
                ? `${dominantZone.label} ${dominantZone.percentage.toFixed(1)}%`
                : "Unavailable"
            }
          />
        </dl>
        {!compact && record.analyticsError ? (
          <p className="mt-2 text-sm text-court-muted">
            Match IQ details are not available for this saved match.
          </p>
        ) : null}
      </div>

      <div className="flex flex-wrap gap-2">
        <Link
          href={`/matches/${record.job.analysis_id}`}
          className="inline-flex items-center gap-2 rounded-md border border-court-line px-3 py-2 text-sm font-semibold text-court-ink hover:bg-court-panel"
        >
          View Match
          <ExternalLink aria-hidden="true" className="h-4 w-4" />
        </Link>
        {matchIqReady ? (
          <ButtonLink href={`/matches/${record.job.analysis_id}/analytics`} variant="secondary">
            <BarChart3 aria-hidden="true" className="h-4 w-4" />
            View Match IQ
          </ButtonLink>
        ) : null}
        {canShare ? (
          <ButtonLink href={`/matches/${record.job.analysis_id}/analytics#share-card`}>
            <Share2 aria-hidden="true" className="h-4 w-4" />
            Share
          </ButtonLink>
        ) : null}
      </div>
    </article>
  );
}

function MatchFact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs font-semibold uppercase tracking-wide text-court-muted">{label}</dt>
      <dd className="mt-1 break-words text-court-ink">{value}</dd>
    </div>
  );
}
