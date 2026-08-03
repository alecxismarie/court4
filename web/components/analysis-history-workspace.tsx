"use client";

import { ExternalLink } from "lucide-react";
import { useMemo, useState } from "react";

import { AnalysisStatusBadge, ContributionBadge } from "@/components/history-badges";
import { ButtonLink } from "@/components/ui/button";
import type { AnalysisHistoryItem } from "@/lib/api/types";
import { toApiUrl } from "@/lib/api/client";
import { AuthenticatedImage } from "@/components/authenticated-image";
import { useAnalysisHistory } from "@/lib/use-history";
import { formatDateTime } from "@/lib/utils";

type Filter = "ALL" | "READY" | "LIMITED" | "UNSUITABLE" | "PROCESSING";

const filters: { key: Filter; label: string }[] = [
  { key: "ALL", label: "All" },
  { key: "READY", label: "Ready" },
  { key: "LIMITED", label: "Limited" },
  { key: "UNSUITABLE", label: "Unsuitable" },
  { key: "PROCESSING", label: "Processing" },
];

export function AnalysisHistoryWorkspace() {
  const history = useAnalysisHistory();
  const [filter, setFilter] = useState<Filter>("ALL");
  const items = useMemo(
    () =>
      (history.data?.items ?? []).filter((item) => {
        if (filter === "ALL") return true;
        return item.status === filter;
      }),
    [filter, history.data?.items],
  );

  return (
    <div className="space-y-6">
      <section className="rounded-md border border-court-line bg-white p-6 shadow-panel">
        <p className="text-sm font-semibold uppercase tracking-wide text-court-green">
          Past reports
        </p>
        <h1 className="mt-2 text-3xl font-semibold text-court-ink">
          Your analysis history
        </h1>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-court-muted">
          Revisit every recording Court4 has processed, including reports with limited
          evidence or unsuitable video.
        </p>
      </section>

      <section aria-label="Analysis filters" className="flex flex-wrap gap-2">
        {filters.map((item) => (
          <button
            key={item.key}
            type="button"
            onClick={() => setFilter(item.key)}
            aria-pressed={filter === item.key}
            className={
              filter === item.key
                ? "rounded-md bg-court-navy px-3 py-2 text-sm font-semibold text-white"
                : "rounded-md border border-court-line bg-white px-3 py-2 text-sm font-semibold text-court-ink hover:bg-court-panel"
            }
          >
            {item.label}
          </button>
        ))}
      </section>

      {history.isLoading ? (
        <HistoryMessage message="Loading your analyses." />
      ) : history.isError ? (
        <HistoryMessage message="Court4 could not load Analysis History. Try again shortly." />
      ) : history.data?.total === 0 ? (
        <HistoryMessage message="No analyses yet. Upload a match recording to create your first Court4 report." />
      ) : items.length === 0 ? (
        <HistoryMessage message="No analyses match this filter." />
      ) : (
        <section className="divide-y divide-court-line rounded-md border border-court-line bg-white shadow-panel">
          {items.map((item) => (
            <AnalysisRow key={item.analysis_id} item={item} />
          ))}
        </section>
      )}
    </div>
  );
}

function AnalysisRow({ item }: { item: AnalysisHistoryItem }) {
  return (
    <article className="grid gap-4 p-5 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center">
      <div className="grid min-w-0 gap-4 sm:grid-cols-[auto_minmax(0,1fr)]">
        {item.thumbnail_url ? (
          <AuthenticatedImage
            src={toApiUrl(item.thumbnail_url)}
            alt={`Preview for ${item.title}`}
            className="h-24 w-full rounded-md border border-court-line object-cover sm:w-36"
          />
        ) : null}
        <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="font-semibold text-court-ink">{item.title}</h2>
          <AnalysisStatusBadge status={item.status} />
          <ContributionBadge status={item.contribution.status} />
        </div>
        <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2 xl:grid-cols-4">
          <Fact label="Analysis date" value={formatDateTime(item.created_at)} />
          <Fact
            label="Video quality"
            value={item.recording_quality ? friendlyQuality(item.recording_quality) : "Not available"}
          />
          <Fact
            label="Observation coverage"
            value={
              item.observation_coverage_ratio === null
                ? "Not available"
                : `${(item.observation_coverage_ratio * 100).toFixed(0)}%`
            }
          />
          <Fact
            label="Measurements / Match IQ"
            value={`${item.measurement_available ? "Available" : "Not available"} / ${
              item.match_iq_available ? "Available" : "Not available"
            }`}
          />
        </dl>
        <p className="mt-3 text-sm leading-6 text-court-muted">
          {item.contribution.explanation}
        </p>
        {item.limitation ? (
          <p className="mt-1 text-sm leading-6 text-court-muted">{item.limitation}</p>
        ) : null}
        </div>
      </div>
      <ButtonLink href={item.report_url} variant="secondary">
        Reopen report
        <ExternalLink aria-hidden="true" className="h-4 w-4" />
      </ButtonLink>
    </article>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs font-semibold uppercase tracking-wide text-court-muted">{label}</dt>
      <dd className="mt-1 break-words text-court-ink">{value}</dd>
    </div>
  );
}

function HistoryMessage({ message }: { message: string }) {
  return (
    <section className="rounded-md border border-court-line bg-white p-8 text-center shadow-panel">
      <p className="text-sm text-court-muted">{message}</p>
    </section>
  );
}

function friendlyQuality(value: string): string {
  return value.charAt(0) + value.slice(1).toLowerCase();
}
