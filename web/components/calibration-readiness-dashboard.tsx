"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, CircleSlash2, ShieldCheck } from "lucide-react";

import {
  type CalibrationReadinessSummary,
  type DashboardMetric,
  getCalibrationReadiness,
} from "@/lib/api/calibration-readiness";
import { cn } from "@/lib/utils";

export function CalibrationReadinessDashboard() {
  const query = useQuery({
    queryKey: ["internal", "calibration-readiness"],
    queryFn: getCalibrationReadiness,
  });

  if (query.isPending) {
    return <p role="status">Loading calibration readiness…</p>;
  }
  if (query.isError) {
    return (
      <section className="rounded-lg border border-red-200 bg-red-50 p-5">
        <h1 className="text-xl font-semibold text-red-800">Readiness data unavailable</h1>
        <p className="mt-2 text-sm text-red-700">
          The internal summary could not be loaded. No calibration action was attempted.
        </p>
      </section>
    );
  }

  return <ReadinessContent summary={query.data} />;
}

function ReadinessContent({ summary }: { summary: CalibrationReadinessSummary }) {
  const dataset = summary.dataset;
  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <header className="rounded-xl border border-court-line bg-white p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-court-muted">
              Internal · read-only · shadow calibration
            </p>
            <h1 className="mt-2 text-3xl font-semibold text-court-ink">
              Calibration readiness
            </h1>
            <p className="mt-2 max-w-3xl text-sm text-court-muted">
              Evidence sufficiency for policy review. This is not validation, scientific
              accuracy, rally detection, or player-facing analytics.
            </p>
          </div>
          <StatusPill value={summary.readiness.verdict} />
        </div>
        <p className="mt-5 rounded-md bg-court-panel p-4 text-sm text-court-ink">
          {summary.readiness.explanation}
        </p>
        {summary.source_status.overall !== "CURRENT" && (
          <Notice title={`${summary.source_status.overall} source data`}>
            {summary.source_status.messages.join(" ")}
          </Notice>
        )}
      </header>

      <Section title="Dataset overview">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Stat label="Total samples" value={dataset.total_samples} />
          <Stat label="Development" value={dataset.development_count} />
          <Stat label="Validation" value={dataset.validation_count} />
          <Stat label="Holdout" value={dataset.holdout_count} warning={dataset.holdout_count === 0} />
        </div>
        <div className="mt-3 grid gap-3 sm:grid-cols-3">
          <Stat label="Fully reviewed" value={dataset.reviewed_samples} />
          <Stat label="Partially reviewed" value={dataset.partially_reviewed_samples} />
          <Stat label="Unreviewed" value={dataset.unreviewed_samples} />
        </div>
      </Section>

      <Section title="Dataset balance">
        <div className="grid gap-3 md:grid-cols-2">
          {summary.balance.categories.map((item) => (
            <article key={item.category} className="rounded-md border border-court-line p-4">
              <h3 className="font-medium capitalize text-court-ink">
                {item.category.replaceAll("_", " ")}
              </h3>
              <p className="mt-2 text-sm text-court-muted">
                {Object.entries(item.counts)
                  .map(([label, count]) => `${label}: ${count}`)
                  .join(" · ") || "No samples"}
              </p>
              {(item.missing.length > 0 || item.underrepresented.length > 0) && (
                <p className="mt-2 text-xs text-amber-800">
                  Missing: {item.missing.join(", ") || "none"} · Underrepresented:{" "}
                  {item.underrepresented.join(", ") || "none"}
                </p>
              )}
            </article>
          ))}
        </div>
      </Section>

      <Section title="Artifact and review readiness">
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="space-y-2">
            {summary.artifact_readiness.map((item) => (
              <KeyValue
                key={item.readiness}
                label={item.readiness.replaceAll("_", " ")}
                value={`${item.count} sample${item.count === 1 ? "" : "s"}`}
              />
            ))}
          </div>
          <div className="space-y-3">
            {summary.review_completion.map((item) => (
              <div key={item.key}>
                <div className="flex justify-between gap-3 text-sm">
                  <span>{item.label}</span>
                  <span className="text-court-muted">
                    {item.reviewed_samples}/{item.total_samples} samples
                  </span>
                </div>
                <div className="mt-1 h-2 overflow-hidden rounded-full bg-slate-200">
                  <div
                    className="h-full bg-court-blue"
                    style={{
                      width: `${item.total_samples ? (item.reviewed_samples / item.total_samples) * 100 : 0}%`,
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      </Section>

      <Section title="Active Play shadow readiness">
        <p className="mb-4 text-sm text-court-muted">
          Shadow estimates only. No rallies, points, serves, shots, or tactical events are
          detected.
        </p>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Stat label="Generated intervals" value={summary.active_play.generated_intervals} />
          <Stat label="Reviewed intervals" value={summary.active_play.reviewed_intervals} />
          <Stat
            label="Reviewed duration"
            value={`${summary.active_play.reviewed_duration_seconds.toFixed(1)}s`}
          />
          <Stat
            label="Current-schema samples"
            value={summary.active_play.current_schema_sample_count}
            warning={summary.active_play.current_schema_sample_count === 0}
          />
        </div>
        <MetricGrid
          metrics={[
            summary.active_play.false_active,
            summary.active_play.false_idle,
            summary.active_play.boundary_error,
            summary.active_play.abstention_rate,
            summary.active_play.coverage_rate,
          ]}
        />
      </Section>

      <Section title="Calibration outcomes">
        <MetricGrid metrics={summary.calibration_outcomes} />
      </Section>

      <Section title="Disagreements and unresolved review">
        <div className="grid gap-3 md:grid-cols-2">
          {summary.disagreements.map((item) => (
            <KeyValue
              key={item.category}
              label={item.label}
              value={item.count === null ? availabilityLabel(item.availability) : item.count}
            />
          ))}
        </div>
        {summary.unresolved_items.length > 0 && (
          <ul className="mt-4 space-y-2 text-sm text-court-muted">
            {summary.unresolved_items.map((item, index) => (
              <li key={`${item.sample_id}-${item.category}-${index}`}>
                {item.sample_id} · {item.category}: {item.reason}
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Policy safety">
        <div className="grid gap-3 md:grid-cols-2">
          <Safety label="Video-quality thresholds immutable" value={summary.policy_safety.recording_policy_immutable} />
          <Safety label="Active Play thresholds immutable" value={summary.policy_safety.active_play_policy_immutable} />
          <Safety label="Holdout protection enabled" value={summary.policy_safety.holdout_protection_enabled} />
          <Safety
            label="Deterministic report hashes"
            value={summary.policy_safety.deterministic_report_status === "MATCH"}
            detail={summary.policy_safety.deterministic_report_status}
          />
          <Safety label="False-active budget approved" value={summary.policy_safety.false_active_budget_approved} />
          <Safety label="False-idle budget approved" value={summary.policy_safety.false_idle_budget_approved} />
        </div>
      </Section>

      <Section title="Decision basis">
        <ListBlock title="Blockers" values={summary.readiness.blockers} />
        <ListBlock title="Warnings" values={summary.readiness.warnings} />
        <ListBlock title="Satisfied criteria" values={summary.readiness.satisfied_criteria} />
        <ListBlock title="Recommended next actions" values={summary.readiness.recommended_actions} />
      </Section>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-court-line bg-white p-5">
      <h2 className="mb-4 text-xl font-semibold text-court-ink">{title}</h2>
      {children}
    </section>
  );
}

function Stat({
  label,
  value,
  warning = false,
}: {
  label: string;
  value: number | string;
  warning?: boolean;
}) {
  return (
    <div className={cn("rounded-md border p-4", warning ? "border-amber-300 bg-amber-50" : "border-court-line")}>
      <p className="text-xs uppercase tracking-wide text-court-muted">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-court-ink">{value}</p>
    </div>
  );
}

function MetricGrid({ metrics }: { metrics: DashboardMetric[] }) {
  return (
    <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {metrics.map((metric) => (
        <article key={metric.key} className="rounded-md border border-court-line p-4">
          <p className="text-sm font-medium text-court-ink">{metric.label}</p>
          <p className="mt-2 text-xl font-semibold">
            {metricValue(metric)}
          </p>
          <p className="mt-1 text-xs text-court-muted">
            {availabilityLabel(metric.availability)}
            {metric.note ? ` · ${metric.note}` : ""}
          </p>
        </article>
      ))}
    </div>
  );
}

function metricValue(metric: DashboardMetric): string {
  if (metric.availability === "NOT_REVIEWED") return "Not reviewed";
  if (metric.availability === "NOT_AVAILABLE") return "Not available";
  if (metric.availability === "STALE") return "Stale";
  if (metric.percentage !== null) return `${metric.percentage.toFixed(1)}%`;
  if (metric.numerator !== null && metric.denominator !== null) {
    return `${metric.numerator}/${metric.denominator}`;
  }
  if (metric.raw_count !== null) return String(metric.raw_count);
  return "Provisional";
}

function availabilityLabel(value: string): string {
  return value.toLowerCase().replaceAll("_", " ");
}

function KeyValue({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-md border border-court-line px-4 py-3 text-sm">
      <span className="capitalize text-court-muted">{label}</span>
      <span className="font-semibold text-court-ink">{value}</span>
    </div>
  );
}

function Safety({
  label,
  value,
  detail,
}: {
  label: string;
  value: boolean;
  detail?: string;
}) {
  return (
    <div className="flex items-center gap-3 rounded-md border border-court-line p-3 text-sm">
      {value ? (
        <CheckCircle2 className="h-5 w-5 text-emerald-700" aria-hidden="true" />
      ) : (
        <CircleSlash2 className="h-5 w-5 text-amber-700" aria-hidden="true" />
      )}
      <span>{label}</span>
      {detail && <span className="ml-auto text-xs text-court-muted">{detail}</span>}
    </div>
  );
}

function StatusPill({ value }: { value: string }) {
  return (
    <span className="inline-flex items-center gap-2 rounded-full bg-court-navy px-4 py-2 text-sm font-semibold text-white">
      <ShieldCheck className="h-4 w-4" aria-hidden="true" />
      {value.replaceAll("_", " ")}
    </span>
  );
}

function Notice({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div role="alert" className="mt-4 flex gap-3 rounded-md border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      <p><strong>{title}.</strong> {children}</p>
    </div>
  );
}

function ListBlock({ title, values }: { title: string; values: string[] }) {
  if (values.length === 0) return null;
  return (
    <div className="mb-4 last:mb-0">
      <h3 className="font-medium text-court-ink">{title}</h3>
      <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-court-muted">
        {values.map((value) => <li key={value}>{value}</li>)}
      </ul>
    </div>
  );
}
