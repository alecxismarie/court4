"use client";

import { ArrowRight, BarChart3, CircleHelp, FileText, Route } from "lucide-react";

import { ButtonLink } from "@/components/ui/button";
import type { PlayHistoryResponse } from "@/lib/api/types";
import { usePlayHistory } from "@/lib/use-history";
import { formatDateTime } from "@/lib/utils";
import { formatTrackedTime } from "@/lib/workspace-data";

type Progress = PlayHistoryResponse["progress"];
type TrendMetric = Progress["trend_metrics"][number];
type ContributingAnalysis = PlayHistoryResponse["comparison_candidates"][number];

const comparisonDisclaimer =
  "Court4 shows differences between similar recordings. A difference alone does not show whether your performance got better or worse.";

export function PlayHistoryWorkspace() {
  const history = usePlayHistory();
  const data = history.data;

  return (
    <div className="space-y-6">
      <section className="rounded-md border border-court-line bg-white p-6 shadow-panel">
        <p className="text-sm font-semibold uppercase tracking-wide text-court-green">
          Long-term observations
        </p>
        <h1 className="mt-2 text-3xl font-semibold text-court-ink">
          Your play over time
        </h1>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-court-muted">
          See how Court4’s qualified movement and court-position observations change across
          comparable analysis reports.
        </p>
      </section>

      {history.isLoading ? (
        <Message message="Reviewing your qualified observations." />
      ) : history.isError || !data ? (
        <Message message="Court4 could not load your Play History. Try again shortly." />
      ) : (
        <ProgressContent data={data} />
      )}
    </div>
  );
}

function ProgressContent({ data }: { data: PlayHistoryResponse }) {
  const progress = data.progress;

  return (
    <>
      <section className="rounded-md border border-court-line bg-white p-6 shadow-panel">
        <div className="flex gap-4">
          <span className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-court-panel text-court-green">
            <CircleHelp aria-hidden="true" className="h-6 w-6" />
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-sm font-semibold uppercase tracking-wide text-court-green">
                How has my play changed?
              </p>
              {progress.provisional ? (
                <NeutralBadge
                  label={
                    progress.baseline_status === "NO_QUALIFIED_REPORTS"
                      ? "Not enough data yet"
                      : "Provisional"
                  }
                />
              ) : null}
            </div>
            <h2 className="mt-2 text-2xl font-semibold text-court-ink">{progress.answer}</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-court-muted">
              {progress.explanation}
            </p>
            <p className="mt-3 text-sm font-medium leading-6 text-court-ink">
              {evidenceContext(progress)}
            </p>
            <p className="mt-3 max-w-3xl rounded-md border border-court-line bg-court-panel p-3 text-xs leading-5 text-court-muted">
              {comparisonDisclaimer}
            </p>
            <BaselineState progress={progress} />
            {progress.limitations.length > 1 ? (
              <details className="mt-4 text-sm text-court-muted">
                <summary className="cursor-pointer font-semibold text-court-ink">
                  {progress.baseline_status === "NO_QUALIFIED_REPORTS"
                    ? "Why no comparison is shown"
                    : "Comparison limitations"}
                </summary>
                <ul className="mt-2 list-disc space-y-1 pl-5">
                  {progress.limitations
                    .filter((limitation) => !limitation.startsWith("These changes describe"))
                    .map((limitation) => (
                      <li key={limitation}>{limitation}</li>
                    ))}
                </ul>
              </details>
            ) : null}
          </div>
        </div>
      </section>

      {progress.trend_metrics.length ? (
        <section className="rounded-md border border-court-line bg-white p-6 shadow-panel">
          <div className="flex items-start gap-3">
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-md bg-court-panel text-court-green">
              <BarChart3 aria-hidden="true" className="h-5 w-5" />
            </span>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-xl font-semibold text-court-ink">
                  Earlier and recent observations
                </h2>
                {progress.provisional ? <NeutralBadge label="Provisional comparison" /> : null}
              </div>
              <p className="mt-1 text-sm leading-6 text-court-muted">
                Qualified reports only. Missing measurements appear as unavailable, never zero.
              </p>
            </div>
          </div>
          <ComparisonGroups progress={progress} />
          <TrendChart metrics={progress.trend_metrics} />
        </section>
      ) : (
        <BaselinePreview progress={progress} />
      )}

      {progress.play_style ? <PlayStyleSection style={progress.play_style} /> : null}

      <ContributingReports
        reports={data.comparison_candidates}
        contributingIds={progress.contributing_analysis_ids}
      />

      <section className="rounded-md border border-court-line bg-white p-6 shadow-panel">
        <h2 className="text-xl font-semibold text-court-ink">
          Latest qualified analysis insights
        </h2>
        <p className="mt-1 text-sm leading-6 text-court-muted">
          Recent observations supported by qualified analysis evidence.
        </p>
        {data.latest_verified_match_iq.length ? (
          <div className="mt-4 grid gap-3">
            {data.latest_verified_match_iq.map((summary) => (
              <article
                key={summary.analysis_id}
                className="rounded-md border border-court-line bg-court-panel p-4"
              >
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <h3 className="font-semibold text-court-ink">{summary.title}</h3>
                  <span className="text-sm text-court-muted">
                    {formatDateTime(summary.created_at)}
                  </span>
                </div>
                <p className="mt-2 text-sm leading-6 text-court-muted">{summary.summary}</p>
                <ButtonLink href={summary.report_url} variant="secondary" className="mt-3">
                  Open analysis
                  <ArrowRight aria-hidden="true" className="h-4 w-4" />
                </ButtonLink>
              </article>
            ))}
          </div>
        ) : (
          <p className="mt-4 text-sm leading-6 text-court-muted">
            No qualified insights are available yet.
          </p>
        )}
      </section>

      <section className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-court-line bg-white p-5 shadow-panel">
        <div>
          <h2 className="font-semibold text-court-ink">Need technical report details?</h2>
          <p className="mt-1 text-sm text-court-muted">
            Video quality, processing status, and contribution decisions stay in Analysis
            History.
          </p>
        </div>
        <ButtonLink href="/analysis-history" variant="secondary">
          View Analysis History
          <ArrowRight aria-hidden="true" className="h-4 w-4" />
        </ButtonLink>
      </section>
    </>
  );
}

function BaselineState({ progress }: { progress: Progress }) {
  if (
    progress.baseline_status === "NO_QUALIFIED_REPORTS" ||
    progress.baseline_status === "MIXED_OR_INCOMPATIBLE_REPORTS" ||
    progress.baseline_status === "COMPARISON_AVAILABLE"
  ) {
    return null;
  }
  const target = 3;
  return (
    <div className="mt-5">
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
        <span className="font-semibold text-court-ink">Baseline evidence</span>
        <span className="text-court-muted">
          {Math.min(progress.comparable_analysis_count, target)} of {target} comparable reports
        </span>
      </div>
      <div
        className="mt-2 h-2 overflow-hidden rounded-full bg-court-panel"
        role="progressbar"
        aria-label="Comparable reports available for the initial baseline"
        aria-valuemin={0}
        aria-valuemax={target}
        aria-valuenow={Math.min(progress.comparable_analysis_count, target)}
      >
        <div
          className="h-full rounded-full bg-court-navy"
          style={{
            width: `${Math.min(100, (progress.comparable_analysis_count / target) * 100)}%`,
          }}
        />
      </div>
    </div>
  );
}

function BaselinePreview({ progress }: { progress: Progress }) {
  const title =
    progress.baseline_status === "BASELINE_ESTABLISHED"
      ? "Your initial baseline"
      : "What will appear here";
  return (
    <section className="rounded-md border border-court-line bg-white p-6 shadow-panel">
      <h2 className="text-xl font-semibold text-court-ink">{title}</h2>
      <p className="mt-2 text-sm leading-6 text-court-muted">
        {progress.baseline_status === "BASELINE_ESTABLISHED"
          ? "Three comparable reports are available. One more comparable report is needed to create two non-overlapping groups of at least two reports."
          : "Once enough compatible evidence is available, Court4 will show neutral, duration-aware comparisons here."}
      </p>
      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <PreviewCard title="Observed changes" text="A neutral summary of what changed." />
        <PreviewCard title="Comparable graphs" text="Earlier and recent qualified observations." />
        <PreviewCard title="Evidence context" text="Report counts, dates, durations, and methods." />
      </div>
    </section>
  );
}

function ComparisonGroups({ progress }: { progress: Progress }) {
  if (!progress.earlier_group || !progress.recent_group) return null;
  return (
    <div className="mt-5 grid gap-3 sm:grid-cols-2">
      {[progress.earlier_group, progress.recent_group].map((group) => (
        <div key={group.name} className="rounded-md border border-court-line bg-court-panel p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-court-muted">
            {group.name} group
          </p>
          <p className="mt-2 font-semibold text-court-ink">
            {formatPeriod(group.period_start, group.period_end)}
          </p>
          <p className="mt-1 text-sm text-court-muted">
            {group.analysis_count} qualified reports ·{" "}
            {formatTrackedTime(group.qualified_observation_seconds)} reliable observation
          </p>
        </div>
      ))}
    </div>
  );
}

function TrendChart({ metrics }: { metrics: TrendMetric[] }) {
  return (
    <div
      className="mt-6 space-y-7"
      role="img"
      aria-label="Neutral graph comparing earlier and recent qualified observations"
    >
      <div className="flex flex-wrap gap-4 text-xs font-semibold text-court-muted">
        <span className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full bg-slate-400" />
          Earlier
        </span>
        <span className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full bg-court-navy" />
          Recent
        </span>
      </div>
      {metrics.map((metric) => (
        <div key={metric.key}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-sm font-semibold text-court-ink">
              {metric.label} ({metric.unit})
            </h3>
            <NeutralBadge label={changeLabel(metric)} />
          </div>
          <div className="mt-3 grid grid-cols-[4rem_minmax(0,1fr)_5.5rem] items-center gap-2 text-xs">
            <GraphBar label="Earlier" value={metric.earlier_value} metric={metric} tone="earlier" />
            <GraphBar label="Recent" value={metric.recent_value} metric={metric} tone="recent" />
          </div>
          <p className="mt-2 text-xs leading-5 text-court-muted">{metric.context}</p>
          <p className="mt-1 text-xs leading-5 text-court-muted">
            {metric.earlier_contributing_count} earlier + {metric.recent_contributing_count} recent
            reports ·{" "}
            {formatTrackedTime(
              metric.earlier_qualified_observation_seconds +
                metric.recent_qualified_observation_seconds,
            )}{" "}
            reliable observation · {metric.aggregation_method}
            {metric.provisional ? " · provisional" : ""}
          </p>
        </div>
      ))}
    </div>
  );
}

function GraphBar({
  label,
  value,
  metric,
  tone,
}: {
  label: string;
  value: number | null;
  metric: TrendMetric;
  tone: "earlier" | "recent";
}) {
  return (
    <>
      <span className="text-court-muted">{label}</span>
      <div
        className={
          value === null
            ? "h-3 rounded-full border border-dashed border-slate-300 bg-transparent"
            : "h-3 overflow-hidden rounded-full bg-court-panel"
        }
      >
        {value !== null ? (
          <div
            className={
              tone === "earlier"
                ? "h-full rounded-full bg-slate-400"
                : "h-full rounded-full bg-court-navy"
            }
            style={{ width: `${barWidth(value, metric)}%` }}
          />
        ) : null}
      </div>
      <span className="text-right font-semibold text-court-ink">
        {formatMetric(value, metric.unit)}
      </span>
    </>
  );
}

function PlayStyleSection({ style }: { style: NonNullable<Progress["play_style"]> }) {
  return (
    <section className="rounded-md border border-court-line bg-white p-6 shadow-panel">
      <div className="flex items-start gap-3">
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-md bg-court-panel text-court-green">
          <Route aria-hidden="true" className="h-5 w-5" />
        </span>
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-xl font-semibold text-court-ink">
              Observed court-position change
            </h2>
            {style.provisional ? <NeutralBadge label="Provisional" /> : null}
          </div>
          <p className="mt-2 text-sm leading-6 text-court-muted">{style.summary}</p>
        </div>
      </div>
      {style.metric_label ? (
        <div className="mt-5 grid gap-3 sm:grid-cols-2">
          <StyleCard period="Earlier group" label={style.metric_label} value={style.earlier_value} />
          <StyleCard period="Recent group" label={style.metric_label} value={style.recent_value} />
        </div>
      ) : null}
      <p className="mt-3 text-xs leading-5 text-court-muted">
        Based on {style.qualified_analysis_count} qualified reports covering{" "}
        {formatTrackedTime(style.qualified_observation_seconds)} of reliable observation.{" "}
        {comparisonDisclaimer}
      </p>
    </section>
  );
}

function ContributingReports({
  reports,
  contributingIds,
}: {
  reports: ContributingAnalysis[];
  contributingIds: string[];
}) {
  const contributing = new Set(contributingIds);
  return (
    <section className="rounded-md border border-court-line bg-white shadow-panel">
      <details>
        <summary className="flex cursor-pointer list-none items-center gap-3 p-5">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-md bg-court-panel text-court-green">
            <FileText aria-hidden="true" className="h-5 w-5" />
          </span>
          <span>
            <span className="block font-semibold text-court-ink">
              Reports considered for this view
            </span>
            <span className="mt-1 block text-sm text-court-muted">
              {contributing.size} supporting reports in the current baseline or comparison
            </span>
          </span>
        </summary>
        {reports.length ? (
          <div className="divide-y divide-court-line border-t border-court-line">
            {reports.map((report) => (
              <article
                key={report.analysis_id}
                className="grid gap-3 px-5 py-4 md:grid-cols-[minmax(0,1fr)_auto] md:items-center"
              >
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="font-semibold text-court-ink">{report.title}</h3>
                    <NeutralBadge label={friendlyContribution(report.contribution_status)} />
                    <NeutralBadge label={friendlyComparability(report.comparability.status)} />
                    {contributing.has(report.analysis_id) ? (
                      <NeutralBadge label="Supports this view" />
                    ) : null}
                  </div>
                  <p className="mt-1 text-sm text-court-muted">
                    {formatDateTime(report.created_at)} ·{" "}
                    {report.qualified_observation_seconds === null
                      ? "Reliable duration unavailable"
                      : `${formatTrackedTime(report.qualified_observation_seconds)} reliable observation`}
                  </p>
                  <p className="mt-2 text-sm leading-6 text-court-muted">
                    {report.comparability.reasons[0]}
                  </p>
                </div>
                <ButtonLink href={report.report_url} variant="secondary">
                  Open analysis
                </ButtonLink>
              </article>
            ))}
          </div>
        ) : (
          <p className="border-t border-court-line p-5 text-sm text-court-muted">
            No qualified reports are available yet.
          </p>
        )}
      </details>
    </section>
  );
}

function PreviewCard({ title, text }: { title: string; text: string }) {
  return (
    <div className="rounded-md border border-court-line bg-court-panel p-4">
      <h3 className="font-semibold text-court-ink">{title}</h3>
      <p className="mt-2 text-sm leading-6 text-court-muted">{text}</p>
    </div>
  );
}

function StyleCard({
  period,
  label,
  value,
}: {
  period: string;
  label: string;
  value: number | null;
}) {
  return (
    <div className="rounded-md border border-court-line bg-court-panel p-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-court-muted">{period}</p>
      <p className="mt-2 font-semibold text-court-ink">{label}</p>
      <p className="mt-1 text-xl font-semibold text-court-ink">
        {value === null ? "Unavailable" : `${value.toFixed(1)}%`}
      </p>
    </div>
  );
}

function NeutralBadge({ label }: { label: string }) {
  return (
    <span className="rounded-full border border-court-line bg-court-panel px-2.5 py-1 text-xs font-semibold text-court-muted">
      {label}
    </span>
  );
}

function evidenceContext(progress: Progress): string {
  if (progress.baseline_status === "NO_QUALIFIED_REPORTS") {
    return "No completed analyses are ready to compare yet.";
  }
  const reports = `${progress.qualified_analysis_count} qualified ${
    progress.qualified_analysis_count === 1 ? "analysis" : "analyses"
  }`;
  const period =
    progress.comparison_period_start && progress.comparison_period_end
      ? ` from ${formatPeriod(progress.comparison_period_start, progress.comparison_period_end)}`
      : "";
  return `Based on ${reports}${period}, covering ${formatTrackedTime(
    progress.qualified_observation_seconds,
  )} of reliable observation.`;
}

function formatPeriod(start: string, end: string): string {
  const formatter = new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
  const startLabel = formatter.format(new Date(start));
  const endLabel = formatter.format(new Date(end));
  return startLabel === endLabel ? startLabel : `${startLabel} – ${endLabel}`;
}

function formatMetric(value: number | null, unit: string): string {
  if (value === null) return "Unavailable";
  return `${value.toFixed(1)}${unit === "%" ? "%" : ` ${unit}`}`;
}

function changeLabel(metric: TrendMetric): string {
  if (metric.direction === null || metric.change_value === null) return "Unavailable";
  if (metric.direction === "STABLE") return "Remained similar";
  const amount = formatMetric(Math.abs(metric.change_value), metric.unit);
  return metric.direction === "HIGHER" ? `Increased by ${amount}` : `Decreased by ${amount}`;
}

function barWidth(value: number, metric: TrendMetric): number {
  const values = [metric.earlier_value, metric.recent_value].filter(
    (candidate): candidate is number => candidate !== null,
  );
  const maximum =
    metric.unit === "%" ? 100 : Math.max(...values, Number.EPSILON) * 1.1;
  return Math.max(value > 0 ? 3 : 0, Math.min(100, (value / maximum) * 100));
}

function friendlyComparability(status: ContributingAnalysis["comparability"]["status"]): string {
  if (status === "ELIGIBLE") return "Comparable";
  if (status === "PROVISIONAL") return "Provisional comparison";
  if (status === "INELIGIBLE") return "Not comparable";
  return "Not evaluated";
}

function friendlyContribution(status: ContributingAnalysis["contribution_status"]): string {
  if (status === "INCLUDED") return "Qualified for Play History";
  if (status === "PROVISIONAL") return "Contribution pending";
  if (status === "EXCLUDED") return "Not used in Play History";
  return "Contribution not evaluated";
}

function Message({ message }: { message: string }) {
  return (
    <section className="rounded-md border border-court-line bg-white p-8 text-center shadow-panel">
      <p className="text-sm text-court-muted">{message}</p>
    </section>
  );
}
