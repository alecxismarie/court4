"use client";

import { RefreshCw } from "lucide-react";
import { useQuery } from "@tanstack/react-query";

import { getAnalytics } from "@/lib/api/analyses";
import { getArtifactUrl, normalizeApiError } from "@/lib/api/client";
import type { AnalyticsReport } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/skeleton";

export function AnalyticsDetails({ analysisId }: { analysisId: string }) {
  const analyticsQuery = useQuery({
    queryKey: ["analysis", analysisId, "analytics"],
    queryFn: () => getAnalytics(analysisId),
  });

  if (analyticsQuery.isLoading) {
    return (
      <div className="space-y-6" role="status" aria-label="Loading analytics">
        <Skeleton className="h-36" />
        <Skeleton className="h-72" />
      </div>
    );
  }

  if (analyticsQuery.isError || !analyticsQuery.data) {
    const error = normalizeApiError(analyticsQuery.error);
    return (
      <div className="rounded-md border border-red-200 bg-red-50 p-6">
        <h1 className="text-xl font-semibold text-court-red">Analytics could not be loaded</h1>
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

  return <AnalyticsReportView report={analyticsQuery.data.analytics} />;
}

function AnalyticsReportView({ report }: { report: AnalyticsReport }) {
  const averagePosition = report.average_court_position
    ? `${report.average_court_position[0].toFixed(1)} ft, ${report.average_court_position[1].toFixed(1)} ft`
    : "Unavailable";

  return (
    <div className="space-y-6">
      <section className="rounded-md border border-court-line bg-white p-6 shadow-panel">
        <p className="text-sm font-semibold uppercase tracking-wide text-court-green">
          Analytics
        </p>
        <h1 className="mt-2 break-all text-3xl font-semibold text-court-ink">
          {report.analysis_id}
        </h1>
        <p className="mt-2 text-sm text-court-muted">
          Selected track {report.selected_player_track_id} - calibration {report.calibration_id}
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
