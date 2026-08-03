"use client";

import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  CircleDot,
  CircleSlash2,
  RefreshCw,
} from "lucide-react";
import type { ReactNode } from "react";

import { RecordingQualityCard } from "@/components/recording-quality-card";
import { ShareCardPanel } from "@/components/share-card-panel";
import { Skeleton } from "@/components/skeleton";
import { Button } from "@/components/ui/button";
import { getAnalysis, getAnalytics } from "@/lib/api/analyses";
import { getArtifactUrl, normalizeApiError } from "@/lib/api/client";
import { AuthenticatedImage } from "@/components/authenticated-image";
import type {
  AnalysisJob,
  AnalyticsReport,
  MatchIQInsight,
  MatchIQReport,
  RecordingQualityAssessment,
} from "@/lib/api/types";

type Confidence = NonNullable<MatchIQReport["confidence"]>;
type ConfidenceRating = Confidence["recording"];
type ConfidenceLevel = "HIGH" | "MODERATE" | "LOW" | "NOT_AVAILABLE";

export function AnalyticsDetails({ analysisId }: { analysisId: string }) {
  const analyticsQuery = useQuery({
    queryKey: ["analysis", analysisId, "analytics"],
    queryFn: () => getAnalytics(analysisId),
  });
  const jobQuery = useQuery({
    queryKey: ["analysis", analysisId],
    queryFn: () => getAnalysis(analysisId),
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
          className="mt-5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-court-blue"
          type="button"
          variant="secondary"
          onClick={() => void analyticsQuery.refetch()}
        >
          <RefreshCw aria-hidden="true" className="h-4 w-4" />
          Retry loading analysis
        </Button>
      </div>
    );
  }

  return (
    <AnalyticsReportView
      report={analyticsQuery.data.analytics}
      matchIQ={analyticsQuery.data.match_iq}
      job={jobQuery.data ?? null}
    />
  );
}

function AnalyticsReportView({
  report,
  matchIQ,
  job,
}: {
  report: AnalyticsReport;
  matchIQ: MatchIQReport | null;
  job: AnalysisJob | null;
}) {
  const assessment = matchIQ?.recording_quality ?? job?.analysis_readiness ?? null;
  const averagePosition = report.average_court_position
    ? `${report.average_court_position[0].toFixed(1)} ft, ${report.average_court_position[1].toFixed(1)} ft`
    : "Unavailable";

  return (
    <div className="space-y-6">
      <RecordingQualityCard
        assessment={assessment}
        title="Video Quality"
        showRetry={assessment?.status === "UNSUITABLE"}
        headingLevel="h1"
      />

      <ObservationCoverage
        report={report}
        assessment={assessment}
        job={job}
        confidence={matchIQ?.confidence?.tracking ?? null}
      />

      <section className="rounded-md border border-court-line bg-white p-6 shadow-panel">
        <p className="text-sm font-semibold uppercase tracking-wide text-court-green">
          What Court4 measured
        </p>
        <h2 className="mt-2 text-2xl font-semibold text-court-ink">
          Movement Measurements
        </h2>
        <p className="mt-2 text-sm leading-6 text-court-muted">
          Continuity-safe movement facts from the player you selected. These values
          describe the reliably tracked sample, not necessarily the full video.
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

      <EvidenceConfidence confidence={matchIQ?.confidence ?? null} />

      <MatchIQSummary matchIQ={matchIQ} />

      {matchIQ?.quality_gate !== "INSUFFICIENT_EVIDENCE" ? (
        <ShareCardPanel report={report} matchIQ={matchIQ} />
      ) : null}

      <section className="rounded-md border border-court-line bg-white p-5 shadow-panel">
        <h2 className="text-xl font-semibold text-court-ink">Observed Court Position</h2>
        <p className="mt-2 text-sm leading-6 text-court-muted">
          These percentages describe where Court4 observed you during the reliably
          tracked sample. They describe court geometry, not whether a position was good
          or bad.
        </p>
        <div className="mt-4 grid gap-3 md:grid-cols-3">
          <ZoneMetric label="Kitchen" value={report.zone_occupancy.kitchen.percentage} />
          <ZoneMetric
            label="Transition"
            value={report.zone_occupancy.transition_zone.percentage}
          />
          <ZoneMetric label="Baseline" value={report.zone_occupancy.baseline_area.percentage} />
        </div>
      </section>

      <MovementMaps report={report} />

      <Limitations report={report} matchIQ={matchIQ} assessment={assessment} />
    </div>
  );
}

function ObservationCoverage({
  report,
  assessment,
  job,
  confidence,
}: {
  report: AnalyticsReport;
  assessment: RecordingQualityAssessment | null;
  job: AnalysisJob | null;
  confidence: ConfidenceRating | null;
}) {
  const totalSeconds =
    job?.upload_preflight?.upload_signals?.duration_seconds ??
    assessment?.upload_signals?.duration_seconds;
  const observedSeconds = report.observed_duration_seconds;
  const legacy = observedSeconds === undefined;
  const valid =
    !legacy &&
    observedSeconds > 0 &&
    totalSeconds !== undefined &&
    totalSeconds > 0 &&
    observedSeconds <= totalSeconds;
  const percentage = valid ? (observedSeconds / totalSeconds) * 100 : null;
  const uncertainSeconds = valid ? totalSeconds - observedSeconds : null;

  return (
    <section className="rounded-md border border-court-line bg-white p-5 shadow-panel">
      <h2 className="text-xl font-semibold text-court-ink">Observation Coverage</h2>
      {valid && percentage !== null ? (
        <>
          <p className="mt-2 text-lg font-semibold text-court-ink">
            Court4 reliably observed {Math.round(percentage)}% of this video.
          </p>
          <progress
            className="mt-4 h-3 w-full overflow-hidden rounded-full accent-court-green"
            max={100}
            value={percentage}
            aria-label={`Observation coverage ${Math.round(percentage)} percent`}
          />
          <dl className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Metric label="Video length" value={formatDuration(totalSeconds)} />
            <Metric label="Reliably observed" value={formatDuration(observedSeconds)} />
            <Metric label="Observation coverage" value={`${Math.round(percentage)}%`} />
            <Metric
              label="Unobserved or uncertain"
              value={formatDuration(uncertainSeconds ?? 0)}
            />
          </dl>
          <p className="mt-4 text-sm text-court-muted">
            Observation confidence:{" "}
            <strong className="font-semibold text-court-ink">
              {confidenceLabel(confidence?.level ?? "NOT_AVAILABLE")}
            </strong>
          </p>
        </>
      ) : (
        <div className="mt-3 rounded-md border border-court-line bg-court-panel p-4">
          <p className="font-semibold text-court-ink">
            {legacy ? "Legacy analysis — coverage unavailable" : "Not available"}
          </p>
          <p className="mt-1 text-sm leading-6 text-court-muted">
            {legacy
              ? "This analysis was created before reliable observation duration was persisted."
              : observedSeconds === 0
                ? "Not enough reliable tracking was available to calculate coverage."
                : "Video length and reliable tracking could not be paired safely."}
          </p>
          {observedSeconds !== undefined && observedSeconds > 0 ? (
            <p className="mt-2 text-sm text-court-muted">
              Reliably observed duration: {formatDuration(observedSeconds)}
            </p>
          ) : null}
        </div>
      )}
      <p className="mt-4 text-sm leading-6 text-court-muted">
        Observation coverage describes where player tracking was reliable. It does not
        indicate how much of the video was live gameplay.
      </p>
    </section>
  );
}

function EvidenceConfidence({ confidence }: { confidence: Confidence | null }) {
  const unavailable: ConfidenceRating = {
    level: "NOT_AVAILABLE",
    rationale: "Confidence evidence was not persisted for this legacy analysis.",
  };
  const dimensions = [
    ["Video", confidence?.recording ?? unavailable],
    ["Tracking", confidence?.tracking ?? unavailable],
    ["Measurement", confidence?.measurement ?? unavailable],
    ["Interpretation", confidence?.interpretation ?? unavailable],
    ["Recommendation", confidence?.recommendation ?? unavailable],
  ] as const;

  return (
    <section className="rounded-md border border-court-line bg-white p-5 shadow-panel">
      <h2 className="text-xl font-semibold text-court-ink">Evidence Confidence</h2>
      <p className="mt-2 max-w-3xl text-sm leading-6 text-court-muted">
        Each stage depends on the evidence before it. Court4 keeps these confidence
        dimensions separate instead of combining them into one score.
      </p>
      <ol
        className="mt-5 grid min-w-0 gap-2 xl:grid-cols-[1fr_auto_1fr_auto_1fr_auto_1fr_auto_1fr]"
        aria-label="Evidence confidence dependency chain"
      >
        {dimensions.map(([label, rating], index) => (
          <li key={label} className="contents">
            <ConfidenceCard label={label} rating={rating} />
            {index < dimensions.length - 1 ? (
              <div
                className="hidden items-center justify-center text-court-muted xl:flex"
                aria-hidden="true"
              >
                <ChevronRight className="h-5 w-5" />
              </div>
            ) : null}
          </li>
        ))}
      </ol>
    </section>
  );
}

function ConfidenceCard({
  label,
  rating,
}: {
  label: string;
  rating: ConfidenceRating;
}) {
  const level = normalizeConfidenceLevel(rating.level);
  const presentation = confidencePresentation(level);
  return (
    <div className="min-w-0 rounded-md border border-court-line bg-court-panel p-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-court-muted">{label}</p>
      <p className={`mt-2 flex items-center gap-2 text-sm font-semibold ${presentation.tone}`}>
        {presentation.icon}
        <span>{confidenceLabel(level)}</span>
      </p>
      <p className="mt-2 break-words text-xs leading-5 text-court-muted">
        {confidenceSupport(label, level)}
      </p>
    </div>
  );
}

function MatchIQSummary({ matchIQ }: { matchIQ: MatchIQReport | null }) {
  if (!matchIQ) {
    return (
      <section className="rounded-md border border-court-line bg-white p-5 shadow-panel">
        <h2 className="text-xl font-semibold text-court-ink">Movement Insight</h2>
        <span className="mt-3 inline-flex rounded-md border border-court-line bg-court-panel px-3 py-1 text-xs font-semibold uppercase tracking-wide text-court-muted">
          Not enough evidence for insight
        </span>
        <p className="mt-3 text-sm leading-6 text-court-muted">
          This legacy analysis has movement measurements, but no persisted evidence for
          a trustworthy movement insight.
        </p>
      </section>
    );
  }

  const suppressed = matchIQ.quality_gate === "INSUFFICIENT_EVIDENCE";
  return (
    <section className="rounded-md border border-court-line bg-white p-5 shadow-panel">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-court-ink">Movement Insight</h2>
          {!suppressed ? (
            <p className="mt-2 max-w-3xl text-sm leading-6 text-court-muted">
              {playerFacingCopy(matchIQ.summary)}
            </p>
          ) : null}
        </div>
        <span className="rounded-md border border-court-line bg-court-panel px-3 py-2 text-xs font-semibold uppercase tracking-wide text-court-green">
          {gateLabel(matchIQ.quality_gate)}
        </span>
      </div>

      {suppressed ? (
        <div className="mt-5 rounded-md border border-court-amber bg-court-panel p-4">
          <h3 className="font-semibold text-court-ink">Why no Match IQ is shown</h3>
          <p className="mt-2 text-sm leading-6 text-court-muted">
            Court4 could measure some movement, but the video and player tracking
            were not reliable enough to generate a trustworthy movement insight.
          </p>
          <p className="mt-2 text-sm leading-6 text-court-muted">
            Your continuity-safe measurements are still available in Movement
            Measurements.
          </p>
        </div>
      ) : null}

      {matchIQ.status === "generated" && !suppressed && matchIQ.insights.length > 0 ? (
        <div className="mt-5 grid gap-4 lg:grid-cols-2">
          {matchIQ.insights.map((insight) => (
            <InsightCard key={insight.id} insight={insight} />
          ))}
        </div>
      ) : null}

      {matchIQ.focus ? (
        <div className="mt-5 rounded-md border border-court-line bg-court-panel p-4">
          <h3 className="text-base font-semibold text-court-ink">
            {playerFacingCopy(matchIQ.focus.title)}
          </h3>
          <p className="mt-2 text-sm leading-6 text-court-muted">
            {playerFacingCopy(matchIQ.focus.statement)}
          </p>
        </div>
      ) : null}
    </section>
  );
}

function InsightCard({ insight }: { insight: MatchIQInsight }) {
  return (
    <article className="min-w-0 rounded-md border border-court-line bg-white p-4">
      <h3 className="break-words text-base font-semibold text-court-ink">{insight.title}</h3>
      <InsightSection title="Observation">
        {playerFacingCopy(insight.observation || insight.statement)}
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
      <InsightSection title="What it may mean">
        {playerFacingCopy(
          insight.interpretation ??
            "Court4 is keeping this as a measurement because the evidence is limited.",
        )}
      </InsightSection>
      <InsightSection title="What to review next">
        {playerFacingCopy(
          insight.action ?? "Review the measurement and video-quality notes together.",
        )}
      </InsightSection>
    </article>
  );
}

function MovementMaps({ report }: { report: AnalyticsReport }) {
  return (
    <section className="rounded-md border border-court-line bg-white p-5 shadow-panel">
      <h2 className="text-xl font-semibold text-court-ink">Movement Maps</h2>
      <p className="mt-2 max-w-3xl text-sm leading-6 text-court-muted">
        Both maps show Court4&apos;s estimated position for the selected player from a
        top-down court view. They do not show the ball&apos;s path or a full-match tactical
        analysis.
      </p>
      <div className="mt-5 grid gap-4 lg:grid-cols-2">
        <AnalyticsImage
          analysisId={report.analysis_id}
          path={`analytics/${report.artifacts.heatmap_png}`}
          label="Observed movement heatmap"
          badge="Measurement only"
        >
          Warmer areas were observed more often and cooler areas less often. Missing
          areas may reflect limited tracking, so read this map alongside the
          video-quality notes.
        </AnalyticsImage>
        <AnalyticsImage
          analysisId={report.analysis_id}
          path={`analytics/${report.artifacts.trajectory_png}`}
          label="Estimated movement path"
          badge="Observed movement"
          legend
        >
          The line follows Court4&apos;s estimated player position over the reliably
          tracked sample. Sudden jumps or unusually straight lines can come from
          tracking or court-calibration uncertainty.
        </AnalyticsImage>
      </div>
    </section>
  );
}

function Limitations({
  report,
  matchIQ,
  assessment,
}: {
  report: AnalyticsReport;
  matchIQ: MatchIQReport | null;
  assessment: RecordingQualityAssessment | null;
}) {
  const groups = groupedLimitations(report, matchIQ, assessment);
  return (
    <section className="rounded-md border border-court-line bg-court-panel p-5">
      <h2 className="text-xl font-semibold text-court-ink">
        Limitations and Video Guidance
      </h2>
      <p className="mt-2 text-sm leading-6 text-court-muted">
        Use these notes when interpreting this sample or preparing another video.
      </p>
      <div className="mt-5 grid gap-4 lg:grid-cols-3">
        {groups.map((group) => (
          <article key={group.title} className="min-w-0 rounded-md border border-court-line bg-white p-4">
            <h3 className="font-semibold text-court-ink">{group.title}</h3>
            <ul className="mt-2 list-disc space-y-2 pl-5 text-sm leading-6 text-court-muted">
              {group.items.map((item) => (
                <li key={item} className="break-words">{item}</li>
              ))}
            </ul>
          </article>
        ))}
      </div>
    </section>
  );
}

function groupedLimitations(
  report: AnalyticsReport,
  matchIQ: MatchIQReport | null,
  assessment: RecordingQualityAssessment | null,
): Array<{ title: string; items: string[] }> {
  const recording: string[] = [];
  const tracking: string[] = [];
  const analysis: string[] = [];
  if (assessment?.status === "UNSUITABLE") {
    recording.push("This video was not suitable for reliable match analysis.");
  } else if (assessment?.status === "LIMITED") {
    recording.push("Video quality limited how much Court4 could interpret.");
  } else if (!assessment) {
    recording.push("Video-quality evidence is unavailable for this legacy analysis.");
  }
  if ((report.source_fragment_count ?? 1) > 1) {
    tracking.push("The selected player was observed across multiple tracked sections.");
  }
  if ((report.unobserved_gap_seconds ?? 0) > 0) {
    tracking.push("Some movement may have occurred during unobserved tracking gaps.");
  }
  for (const warning of report.continuity_warnings ?? []) {
    tracking.push(friendlyContinuityWarning(warning));
  }
  for (const limitation of [
    ...(matchIQ?.limitations ?? []),
    ...(matchIQ?.insights.flatMap((insight) => insight.limitations) ?? []),
  ]) {
    const normalized = limitation.toLowerCase();
    const friendlyLimitation = playerFacingCopy(limitation);
    if (/(recording|video|camera|visible|resolution)/.test(normalized)) {
      recording.push(friendlyLimitation);
    } else if (/(track|fragment|gap|continuity|candidate)/.test(normalized)) {
      tracking.push(friendlyLimitation);
    } else analysis.push(friendlyLimitation);
  }
  analysis.push(
    "Court4 did not evaluate shots, serves, rallies, ball movement, opponents, scoring, outcomes, tactics, or intent.",
    "Zone labels describe court geometry, not whether positioning was good or bad.",
  );
  if (tracking.length === 0) {
    tracking.push("No additional tracking limitation was persisted for this sample.");
  }
  if (recording.length === 0) {
    recording.push("No additional video limitation was persisted for this sample.");
  }
  return [
    { title: "Video limitations", items: unique(recording) },
    { title: "Tracking limitations", items: unique(tracking) },
    { title: "Analysis limitations", items: unique(analysis) },
  ];
}

function InsightSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="mt-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-court-muted">{title}</p>
      <p className="mt-1 break-words text-sm leading-6 text-court-muted">{children}</p>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-md border border-court-line bg-court-panel p-3">
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
  badge,
  legend = false,
  children,
}: {
  analysisId: string;
  path: string;
  label: string;
  badge: string;
  legend?: boolean;
  children: ReactNode;
}) {
  return (
    <figure className="min-w-0 overflow-hidden rounded-md border border-court-line bg-white">
      <div className="aspect-[10/22] bg-court-panel">
        <AuthenticatedImage
          src={getArtifactUrl(analysisId, path)}
          alt={label}
          className="h-full w-full object-contain"
        />
      </div>
      <figcaption className="border-t border-court-line p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="font-semibold text-court-ink">{label}</span>
          <span className="rounded-md border border-court-line bg-court-panel px-2 py-1 text-xs font-semibold uppercase tracking-wide text-court-green">
            {badge}
          </span>
        </div>
        {legend ? (
          <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-xs font-medium text-court-ink">
            <span className="inline-flex items-center gap-2">
              <span aria-hidden="true" className="h-3 w-3 rounded-full bg-court-green" />
              Tracking started here
            </span>
            <span className="inline-flex items-center gap-2">
              <span aria-hidden="true" className="h-3 w-3 rounded-full bg-court-red" />
              Tracking ended here
            </span>
          </div>
        ) : null}
        <p className="mt-3 break-words text-sm leading-6 text-court-muted">{children}</p>
      </figcaption>
    </figure>
  );
}

function gateLabel(gate: MatchIQReport["quality_gate"]): string {
  if (gate === "NORMAL") return "Verified movement insight";
  if (gate === "CAUTIOUS") return "Limited movement insight";
  if (gate === "MEASUREMENT_ONLY") return "Measurement only";
  return "Not enough evidence for insight";
}

function normalizeConfidenceLevel(level: string): ConfidenceLevel {
  if (level === "HIGH" || level === "MODERATE" || level === "LOW") return level;
  return "NOT_AVAILABLE";
}

function confidenceLabel(level: string): string {
  return level === "NOT_AVAILABLE" ? "Unavailable" : level[0] + level.slice(1).toLowerCase();
}

function confidencePresentation(level: ConfidenceLevel): {
  tone: string;
  icon: ReactNode;
} {
  if (level === "HIGH") {
    return {
      tone: "text-court-green",
      icon: <CheckCircle2 aria-hidden="true" className="h-4 w-4 shrink-0" />,
    };
  }
  if (level === "MODERATE") {
    return {
      tone: "text-court-blue",
      icon: <CircleDot aria-hidden="true" className="h-4 w-4 shrink-0" />,
    };
  }
  if (level === "LOW") {
    return {
      tone: "text-court-amber",
      icon: <AlertTriangle aria-hidden="true" className="h-4 w-4 shrink-0" />,
    };
  }
  return {
    tone: "text-court-muted",
    icon: <CircleSlash2 aria-hidden="true" className="h-4 w-4 shrink-0" />,
  };
}

function confidenceSupport(label: string, level: ConfidenceLevel): string {
  if (level === "NOT_AVAILABLE") return `${label} confidence was not available.`;
  if (label === "Video") {
    return level === "LOW"
      ? "Video quality limits every later stage."
      : "The video supported the evidence that follows.";
  }
  if (label === "Tracking") {
    return level === "LOW"
      ? "Tracking gaps or fragments limit later measurements."
      : "Player tracking supported movement measurement.";
  }
  if (label === "Measurement") {
    return level === "LOW"
      ? "Only limited movement measurement was supported."
      : "Observed positions supported the reported measurements.";
  }
  if (label === "Interpretation") {
    return level === "LOW"
      ? "Only a cautious description is supported."
      : "The evidence supports a bounded movement description.";
  }
  return level === "LOW"
    ? "The evidence limits what Court4 can suggest reviewing."
    : "Court4 can suggest evidence to review, not tactical coaching.";
}

function friendlyContinuityWarning(warning: string): string {
  if (warning === "movement_combines_multiple_track_fragments") {
    return "The movement sample combines multiple tracked sections.";
  }
  if (warning === "unobserved_gaps_not_interpolated") {
    return "Court4 left unobserved gaps unmeasured instead of guessing movement.";
  }
  return "Some tracking continuity could not be verified.";
}

function formatDuration(seconds: number): string {
  const rounded = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(rounded / 60);
  const remaining = rounded % 60;
  return minutes > 0 ? `${minutes}m ${remaining}s` : `${remaining}s`;
}

function unique(items: string[]): string[] {
  return [...new Set(items)];
}

function playerFacingCopy(value: string): string {
  return value
    .replace(/\brecording-quality\b/gi, "video quality")
    .replace(/\brecordings\b/gi, "videos")
    .replace(/\brecording\b/gi, "video");
}
