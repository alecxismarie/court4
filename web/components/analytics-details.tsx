"use client";

import { RefreshCw } from "lucide-react";
import { useQuery } from "@tanstack/react-query";

import { getAnalytics } from "@/lib/api/analyses";
import { getArtifactUrl, normalizeApiError } from "@/lib/api/client";
import type { AnalyticsReport, MatchIQInsight, MatchIQReport } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/skeleton";
import { ShareCardPanel } from "@/components/share-card-panel";

export function AnalyticsDetails({ analysisId }: { analysisId: string }) {
  const analyticsQuery = useQuery({
    queryKey: ["analysis", analysisId, "analytics"],
    queryFn: () => getAnalytics(analysisId),
  });

  if (analyticsQuery.isLoading) {
    return (
      <div className="space-y-6" role="status" aria-label="Loading Match IQ">
        <Skeleton className="h-36" />
        <Skeleton className="h-72" />
      </div>
    );
  }

  if (analyticsQuery.isError || !analyticsQuery.data) {
    const error = normalizeApiError(analyticsQuery.error);
    return (
      <div className="rounded-md border border-red-200 bg-red-50 p-6">
        <h1 className="text-xl font-semibold text-court-red">Match IQ could not be loaded</h1>
        <p className="mt-2 text-sm text-court-red">{error.message}</p>
        <Button
          className="mt-5"
          type="button"
          variant="secondary"
          onClick={() => void analyticsQuery.refetch()}
        >
          <RefreshCw aria-hidden="true" className="h-4 w-4" />
          Retry
        </Button>
      </div>
    );
  }

  return (
    <AnalyticsReportView
      report={analyticsQuery.data.analytics}
      matchIQ={analyticsQuery.data.match_iq}
    />
  );
}

function AnalyticsReportView({
  report,
  matchIQ,
}: {
  report: AnalyticsReport;
  matchIQ: MatchIQReport | null;
}) {
  const averagePosition = report.average_court_position
    ? `${report.average_court_position[0].toFixed(1)} ft, ${report.average_court_position[1].toFixed(1)} ft`
    : "Unavailable";

  return (
    <div className="space-y-6">
      <section className="rounded-md border border-court-line bg-white p-6 shadow-panel">
        <p className="text-sm font-semibold uppercase tracking-wide text-court-green">
          Your Match IQ
        </p>
        <h1 className="mt-2 break-all text-3xl font-semibold text-court-ink">
          {report.analysis_id}
        </h1>
        <p className="mt-2 text-sm text-court-muted">Movement facts from your selected player.</p>
        <dl className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <Metric label="Distance" value={`${report.distance.total_distance_feet.toFixed(1)} ft`} />
          <Metric
            label="Distance meters"
            value={`${report.distance.total_distance_meters.toFixed(1)} m`}
          />
          <Metric
            label="Average movement"
            value={`${report.distance.average_movement_feet_per_second.toFixed(2)} ft/s`}
          />
          <Metric label="Average position" value={averagePosition} />
        </dl>
        <details className="mt-5 text-sm text-court-muted">
          <summary className="cursor-pointer font-semibold text-court-ink">Technical details</summary>
          <dl className="mt-3 grid gap-3 sm:grid-cols-2">
            <div>
              <dt className="font-semibold text-court-ink">Selected track ID</dt>
              <dd>{report.selected_player_track_id}</dd>
            </div>
            <div>
              <dt className="font-semibold text-court-ink">Calibration source</dt>
              <dd>{report.calibration_id}</dd>
            </div>
          </dl>
        </details>
      </section>

      <MatchIQSummary matchIQ={matchIQ} />

      <ShareCardPanel report={report} matchIQ={matchIQ} />

      <section className="rounded-md border border-court-line bg-white p-5 shadow-panel">
        <h2 className="text-lg font-semibold text-court-ink">Zone occupancy</h2>
        <div className="mt-4 grid gap-3 md:grid-cols-3">
          <ZoneMetric label="Kitchen" value={report.zone_occupancy.kitchen.percentage} />
          <ZoneMetric
            label="Transition"
            value={report.zone_occupancy.transition_zone.percentage}
          />
          <ZoneMetric label="Baseline" value={report.zone_occupancy.baseline_area.percentage} />
        </div>
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <AnalyticsImage
          analysisId={report.analysis_id}
          path={`analytics/${report.artifacts.heatmap_png}`}
          label="Heatmap"
        />
        <AnalyticsImage
          analysisId={report.analysis_id}
          path={`analytics/${report.artifacts.trajectory_png}`}
          label="Trajectory"
        />
      </section>
    </div>
  );
}

function MatchIQSummary({ matchIQ }: { matchIQ: MatchIQReport | null }) {
  if (!matchIQ) {
    return (
      <section className="rounded-md border border-court-line bg-white p-5 shadow-panel">
        <h2 className="text-lg font-semibold text-court-ink">Match IQ Summary</h2>
        <p className="mt-2 text-sm leading-6 text-court-muted">
          Match IQ was not generated for this analysis.
        </p>
      </section>
    );
  }

  return (
    <section className="rounded-md border border-court-line bg-white p-5 shadow-panel">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-court-ink">Match IQ Summary</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-court-muted">{matchIQ.summary}</p>
        </div>
        <span className="rounded-md bg-court-panel px-3 py-2 text-xs font-semibold uppercase tracking-wide text-court-green">
          {matchIQ.engine_version}
        </span>
      </div>

      {matchIQ.status === "generated" && matchIQ.insights.length > 0 ? (
        <div className="mt-5 grid gap-4 lg:grid-cols-2">
          {matchIQ.insights.map((insight) => (
            <InsightCard key={insight.id} insight={insight} />
          ))}
        </div>
      ) : null}

      {matchIQ.focus ? (
        <div className="mt-5 rounded-md border border-court-line bg-court-panel p-4">
          <h3 className="text-base font-semibold text-court-ink">{matchIQ.focus.title}</h3>
          <p className="mt-2 text-sm leading-6 text-court-muted">{matchIQ.focus.statement}</p>
          <p className="mt-3 text-xs font-semibold uppercase tracking-wide text-court-muted">
            Supported by {matchIQ.focus.supporting_insight_ids.join(", ")}
          </p>
        </div>
      ) : null}

      {matchIQ.limitations.length > 0 ? (
        <div className="mt-5">
          <h3 className="text-sm font-semibold text-court-ink">Limitations</h3>
          <ul className="mt-2 space-y-1 text-sm leading-6 text-court-muted">
            {matchIQ.limitations.map((limitation) => (
              <li key={limitation}>{limitation}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

function InsightCard({ insight }: { insight: MatchIQInsight }) {
  const primaryEvidence = insight.evidence[0] ?? null;

  return (
    <article className="rounded-md border border-court-line bg-white p-4">
      <div className="flex items-start justify-between gap-3">
        <h3 className="text-base font-semibold text-court-ink">{insight.title}</h3>
        <span className="rounded-md bg-court-panel px-2 py-1 text-xs font-semibold text-court-muted">
          P{insight.priority}
        </span>
      </div>
      <p className="mt-2 text-sm leading-6 text-court-muted">{insight.statement}</p>
      {primaryEvidence ? (
        <dl className="mt-3 rounded-md bg-court-panel p-3">
          <dt className="text-xs font-semibold uppercase tracking-wide text-court-muted">
            Supporting metric
          </dt>
          <dd className="mt-1 text-sm font-semibold text-court-ink">
            {primaryEvidence.label}: {primaryEvidence.formatted_value}
          </dd>
        </dl>
      ) : null}
      <details className="mt-4 text-sm text-court-muted">
        <summary className="cursor-pointer font-semibold text-court-ink">
          Why Court4 said this
        </summary>
        <dl className="mt-3 space-y-3">
          <div>
            <dt className="font-semibold text-court-ink">Rule ID</dt>
            <dd>{insight.rule_id}</dd>
          </div>
          {insight.evidence.map((evidence) => (
            <div key={`${insight.id}-${evidence.metric}`}>
              <dt className="font-semibold text-court-ink">{evidence.label}</dt>
              <dd>
                {evidence.metric}: {evidence.formatted_value}
              </dd>
              <dd>Rule threshold: {evidence.threshold}</dd>
            </div>
          ))}
        </dl>
      </details>
    </article>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-court-line bg-court-panel p-3">
      <dt className="text-xs font-semibold uppercase tracking-wide text-court-muted">{label}</dt>
      <dd className="mt-1 break-words text-sm font-medium text-court-ink">{value}</dd>
    </div>
  );
}

function ZoneMetric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border border-court-line bg-court-panel p-4">
      <p className="text-sm font-semibold text-court-ink">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-court-green">{value.toFixed(1)}%</p>
    </div>
  );
}

function AnalyticsImage({
  analysisId,
  path,
  label,
}: {
  analysisId: string;
  path: string;
  label: string;
}) {
  return (
    <figure className="overflow-hidden rounded-md border border-court-line bg-white shadow-panel">
      <div className="aspect-[10/22] bg-court-panel">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={getArtifactUrl(analysisId, path)}
          alt={label}
          className="h-full w-full object-contain"
        />
      </div>
      <figcaption className="border-t border-court-line px-4 py-3 text-sm font-semibold text-court-ink">
        {label}
      </figcaption>
    </figure>
  );
}
