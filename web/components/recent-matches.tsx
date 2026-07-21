"use client";

import { useQueries } from "@tanstack/react-query";
import { ExternalLink, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { getAnalysis } from "@/lib/api/analyses";
import { normalizeApiError } from "@/lib/api/client";
import type { AnalysisJob } from "@/lib/api/types";
import { getRecentAnalysisIds } from "@/lib/recent-analyses";
import { formatDateTime, shortenAnalysisId } from "@/lib/utils";
import { ButtonLink } from "@/components/ui/button";
import { EmptyState } from "@/components/empty-state";
import { getStageLabel, getStatusLabel } from "@/components/job-status";

export function RecentMatches({ compact = false }: { compact?: boolean }) {
  const [analysisIds, setAnalysisIds] = useState<string[]>([]);

  useEffect(() => {
    setAnalysisIds(getRecentAnalysisIds());
  }, []);

  const queries = useQueries({
    queries: analysisIds.map((analysisId) => ({
      queryKey: ["analysis", analysisId],
      queryFn: () => getAnalysis(analysisId),
    })),
  });

  if (analysisIds.length === 0) {
    return (
      <EmptyState
        title="No recent matches"
        description="Uploaded analysis IDs will be remembered locally in this browser for quick access."
        action={<ButtonLink href="/matches/upload">Upload Match</ButtonLink>}
      />
    );
  }

  return (
    <section className="rounded-md border border-court-line bg-white shadow-panel">
      <div className="border-b border-court-line px-5 py-4">
        <h2 className="text-lg font-semibold text-court-ink">Recent matches</h2>
        <p className="text-sm text-court-muted">Stored locally in this browser.</p>
      </div>
      <div className="divide-y divide-court-line">
        {queries.map((query, index) => {
          const analysisId = analysisIds[index];
          if (query.isLoading) {
            return (
              <div key={analysisId} className="px-5 py-4 text-sm text-court-muted">
                Loading {shortenAnalysisId(analysisId)}...
              </div>
            );
          }
          if (query.isError || !query.data) {
            const error = normalizeApiError(query.error);
            return (
              <div key={analysisId} className="flex items-center justify-between gap-3 px-5 py-4">
                <div>
                  <p className="font-medium text-court-ink">{shortenAnalysisId(analysisId)}</p>
                  <p className="text-sm text-court-red">{error.message}</p>
                </div>
                <button
                  type="button"
                  onClick={() => void query.refetch()}
                  className="inline-flex items-center gap-2 rounded-md border border-court-line px-3 py-2 text-sm font-semibold text-court-ink"
                >
                  <RefreshCw aria-hidden="true" className="h-4 w-4" />
                  Retry
                </button>
              </div>
            );
          }
          return <RecentMatchRow key={analysisId} job={query.data} compact={compact} />;
        })}
      </div>
    </section>
  );
}

function RecentMatchRow({ job, compact }: { job: AnalysisJob; compact: boolean }) {
  return (
    <article className="flex flex-wrap items-center justify-between gap-4 px-5 py-4">
      <div className="min-w-0">
        <p className="font-semibold text-court-ink">{shortenAnalysisId(job.analysis_id)}</p>
        <p className="text-sm text-court-muted">
          {getStatusLabel(job.status)} - {getStageLabel(job.current_stage)}
        </p>
        {!compact ? (
          <p className="mt-1 text-xs text-court-muted">Created {formatDateTime(job.created_at)}</p>
        ) : null}
      </div>
      <Link
        href={`/matches/${job.analysis_id}`}
        className="inline-flex items-center gap-2 rounded-md border border-court-line px-3 py-2 text-sm font-semibold text-court-ink hover:bg-court-panel"
      >
        Open Match
        <ExternalLink aria-hidden="true" className="h-4 w-4" />
      </Link>
    </article>
  );
}
