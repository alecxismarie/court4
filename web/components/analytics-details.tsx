"use client";

import { RefreshCw } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { getAnalytics } from "@/lib/api/analyses";
import { getArtifactUrl, normalizeApiError } from "@/lib/api/client";
import type { AnalyticsReport, MatchIQInsight, MatchIQReport } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/skeleton";
import { ShareCardPanel } from "@/components/share-card-panel";
import { RecordingQualityCard } from "@/components/recording-quality-card";

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
      <RecordingQualityCard
        assessment={matchIQ?.recording_quality ?? null}
        title="Recording quality"
        showRetry={matchIQ?.recording_quality?.status === "UNSUITABLE"}
      />

      <section className="rounded-md border border-court-line bg-white p-6 shadow-panel">
        <p className="text-sm font-semibold uppercase tracking-wide text-court-green">
          What Court4 observed
        </p>
        <h1 className="mt-2 text-3xl font-semibold text-court-ink">Movement measurements</h1>
        <p className="mt-2 text-sm text-court-muted">
          Continuity-safe movement facts from the player you selected.
        </p>
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
      </section>

      <MatchIQSummary matchIQ={matchIQ} />

      {matchIQ?.quality_gate !== "INSUFFICIENT_EVIDENCE" ? (
        <ShareCardPanel report={report} matchIQ={matchIQ} />
      ) : null}

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

      <section className="rounded-md border border-court-line bg-court-panel p-5">
        <h2 className="text-lg font-semibold text-court-ink">
          How to read your movement maps
        </h2>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-court-muted">
          Both maps show Court4&apos;s estimate of the selected player&apos;s position from
          a top-down court view. They show player movement, not the ball&apos;s path.
        </p>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <div className="rounded-md border border-court-line bg-white p-4">
            <h3 className="font-semibold text-court-ink">Heatmap</h3>
            <p className="mt-2 text-sm leading-6 text-court-muted">
              Shows where you spent time. Red and yellow areas were visited most often;
              blue areas were visited less often.
            </p>
          </div>
          <div className="rounded-md border border-court-line bg-white p-4">
            <h3 className="font-semibold text-court-ink">Trajectory</h3>
            <p className="mt-2 text-sm leading-6 text-court-muted">
              Shows your estimated path over time. The green dot marks where tracking
              started, the orange line follows your movement, and the red dot marks where
              tracking ended.
            </p>
          </div>
        </div>
        <p className="mt-4 text-sm leading-6 text-court-muted">
          Sudden jumps or unusually straight lines can come from brief tracking or
          court-recognition errors, so read these maps alongside the recording-quality
          notes and limitations.
        </p>
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
        <h2 className="text-lg font-semibold text-court-ink">Movement insight</h2>
        <p className="mt-2 text-sm leading-6 text-court-muted">
          No verified insight yet. Movement measurements remain available above.
        </p>
      </section>
    );
  }

  return (
    <section className="rounded-md border border-court-line bg-white p-5 shadow-panel">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-court-ink">Movement insight</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-court-muted">{matchIQ.summary}</p>
        </div>
        <span className="rounded-md bg-court-panel px-3 py-2 text-xs font-semibold uppercase tracking-wide text-court-green">
          {gateLabel(matchIQ.quality_gate)}
        </span>
      </div>

      {matchIQ.quality_gate === "INSUFFICIENT_EVIDENCE" ? (
        <div className="mt-5 rounded-md border border-amber-200 bg-amber-50 p-4">
          <h3 className="font-semibold text-court-ink">Normal Match IQ is suppressed</h3>
          <p className="mt-1 text-sm text-court-muted">
            This recording does not contain enough dependable evidence for insight cards.
          </p>
        </div>
      ) : null}

      {matchIQ.status === "generated" &&
      matchIQ.quality_gate !== "INSUFFICIENT_EVIDENCE" &&
      matchIQ.insights.length > 0 ? (
        <div className="mt-5 grid gap-4 lg:grid-cols-2">
          {matchIQ.insights.map((insight) => (
            <InsightCard key={insight.id} insight={insight} />
          ))}
        </div>
      ) : null}

      {matchIQ.confidence ? <ConfidenceGrid confidence={matchIQ.confidence} /> : null}

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
  return (
    <article className="rounded-md border border-court-line bg-white p-4">
      <h3 className="text-base font-semibold text-court-ink">{insight.title}</h3>

      <InsightSection title="Observation">
        {insight.observation || insight.statement}
      </InsightSection>

      <div className="mt-4">
        <p className="text-xs font-semibold uppercase tracking-wide text-court-muted">Evidence</p>
        <dl className="mt-2 space-y-2 rounded-md bg-court-panel p-3">
          {insight.evidence.map((evidence) => (
            <div key={`${insight.id}-${evidence.metric}`}>
              <dt className="text-sm font-semibold text-court-ink">{evidence.label}</dt>
              <dd className="text-sm text-court-muted">{evidence.formatted_value}</dd>
            </div>
          ))}
        </dl>
      </div>

      <InsightSection title="Confidence">
        {insight.confidence
          ? `Measurement ${confidenceLabel(insight.confidence.measurement.level)}; tracking ${confidenceLabel(insight.confidence.tracking.level)}.`
          : "Confidence evidence is unavailable for this legacy insight."}
      </InsightSection>

      {insight.interpretation ? (
        <InsightSection title="What it may mean">{insight.interpretation}</InsightSection>
      ) : (
        <InsightSection title="What it may mean">
          Interpretation is suppressed because the evidence is limited.
        </InsightSection>
      )}

      <div className="mt-4">
        <p className="text-xs font-semibold uppercase tracking-wide text-court-muted">
          Limitations
        </p>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-court-muted">
          {insight.limitations.map((limitation) => (
            <li key={limitation}>{limitation}</li>
          ))}
        </ul>
      </div>

      <InsightSection title="What to review next">
        {insight.action ?? "No next-step advice is shown for this evidence level."}
      </InsightSection>
    </article>
  );
}

function InsightSection({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="mt-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-court-muted">{title}</p>
      <p className="mt-1 text-sm leading-6 text-court-muted">{children}</p>
    </div>
  );
}

function ConfidenceGrid({
  confidence,
}: {
  confidence: NonNullable<MatchIQReport["confidence"]>;
}) {
  const dimensions = [
    ["Recording", confidence.recording],
    ["Tracking", confidence.tracking],
    ["Measurement", confidence.measurement],
    ["Interpretation", confidence.interpretation],
    ["Recommendation", confidence.recommendation],
  ] as const;
  return (
    <div className="mt-5">
      <h3 className="text-sm font-semibold text-court-ink">Confidence</h3>
      <dl className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        {dimensions.map(([label, rating]) => (
          <div key={label} className="rounded-md border border-court-line bg-court-panel p-3">
            <dt className="text-xs font-semibold uppercase tracking-wide text-court-muted">
              {label}
            </dt>
            <dd className="mt-1 text-sm font-semibold text-court-ink">
              {confidenceLabel(rating.level)}
            </dd>
            <dd className="mt-1 text-xs leading-5 text-court-muted">{rating.rationale}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function confidenceLabel(level: string): string {
  return level.toLowerCase().replaceAll("_", " ");
}

function gateLabel(gate: MatchIQReport["quality_gate"]): string {
  if (gate === "NORMAL") return "Verified movement insight";
  if (gate === "CAUTIOUS") return "Analysis under review";
  if (gate === "MEASUREMENT_ONLY") return "Limited by recording quality";
  return "Insufficient evidence";
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
