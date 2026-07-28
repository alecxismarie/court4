import { AlertTriangle, CheckCircle2, Info, XCircle } from "lucide-react";
import type { ReactNode } from "react";

import type { RecordingQualityAssessment } from "@/lib/api/types";
import { ButtonLink } from "@/components/ui/button";

type QualityCheck = RecordingQualityAssessment["passed_checks"][number];
type CheckKind = "passed" | "warning" | "failure";

export function RecordingQualityCard({
  assessment,
  title,
  showRetry = false,
  headingLevel = "h2",
}: {
  assessment: RecordingQualityAssessment | null;
  title: string;
  showRetry?: boolean;
  headingLevel?: "h1" | "h2";
}) {
  const Heading = headingLevel;
  if (!assessment) {
    return (
      <section className="rounded-md border border-court-line bg-white p-5 shadow-panel">
        <Heading className="text-2xl font-semibold text-court-ink">{title}</Heading>
        <div className="mt-3 flex items-start gap-2 text-sm text-court-muted">
          <Info aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />
          <p>Legacy analysis — video-quality evidence is unavailable.</p>
        </div>
      </section>
    );
  }

  const tone =
    assessment.status === "UNSUITABLE"
      ? "border-court-red text-court-red"
      : assessment.status === "LIMITED"
        ? "border-court-amber text-court-amber"
        : "border-court-green text-court-green";

  return (
    <section className="rounded-md border border-court-line bg-white p-5 shadow-panel">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Heading className="text-2xl font-semibold text-court-ink">{title}</Heading>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-court-muted">
            {qualitySummary(assessment.status)}
          </p>
        </div>
        <span
          className={`inline-flex items-center gap-2 rounded-md border bg-white px-3 py-1 text-sm font-semibold ${tone}`}
          aria-label={`Video quality: ${qualityLabel(assessment.status)}`}
        >
          {assessment.status === "UNSUITABLE" ? (
            <XCircle aria-hidden="true" className="h-4 w-4" />
          ) : assessment.status === "LIMITED" ? (
            <AlertTriangle aria-hidden="true" className="h-4 w-4" />
          ) : (
            <CheckCircle2 aria-hidden="true" className="h-4 w-4" />
          )}
          {qualityLabel(assessment.status)}
        </span>
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-3">
        <QualityList
          title="What worked"
          checks={assessment.passed_checks}
          kind="passed"
          icon={<CheckCircle2 aria-hidden="true" className="h-4 w-4 text-court-green" />}
          empty="No reliable video checks were available."
        />
        <QualityList
          title="What may limit this analysis"
          checks={assessment.warnings}
          kind="warning"
          icon={<AlertTriangle aria-hidden="true" className="h-4 w-4 text-court-amber" />}
          empty="No video warnings were found."
        />
        <QualityList
          title="Why reliable insight is unavailable"
          checks={assessment.blocking_failures}
          kind="failure"
          icon={<XCircle aria-hidden="true" className="h-4 w-4 text-court-red" />}
          empty="No issues blocked reliable insight."
        />
      </div>

      {assessment.guidance.length > 0 || showRetry ? (
        <div className="mt-5 rounded-md border border-court-line bg-court-panel p-4">
          <h3 className="text-sm font-semibold text-court-ink">
            How to improve the next video
          </h3>
          {assessment.guidance.length > 0 ? (
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm leading-6 text-court-muted">
              {assessment.guidance.map((item) => (
                <li key={item}>{friendlyGuidance(item)}</li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-sm text-court-muted">
              Keep the full court visible and record a continuous section of gameplay.
            </p>
          )}
          {showRetry ? (
            <ButtonLink
              className="mt-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-court-blue"
              href="/upload-match"
              aria-label="Try another video"
            >
              Try another video
            </ButtonLink>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

function QualityList({
  title,
  checks,
  kind,
  icon,
  empty,
}: {
  title: string;
  checks: QualityCheck[];
  kind: CheckKind;
  icon: ReactNode;
  empty: string;
}) {
  return (
    <div className="min-w-0">
      <h3 className="text-sm font-semibold text-court-ink">{title}</h3>
      {checks.length > 0 ? (
        <ul className="mt-2 space-y-2 text-sm leading-6 text-court-muted">
          {checks.map((check) => (
            <li key={check.code} className="flex min-w-0 items-start gap-2">
              <span className="mt-1 shrink-0">{icon}</span>
              <span className="min-w-0 break-words">{friendlyCheckMessage(check, kind)}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-sm leading-6 text-court-muted">{empty}</p>
      )}
    </div>
  );
}

function qualitySummary(status: RecordingQualityAssessment["status"]): string {
  if (status === "UNSUITABLE") {
    return "This video isn’t suitable for reliable match analysis.";
  }
  if (status === "LIMITED") {
    return "Court4 measured part of this video, but some evidence is limited.";
  }
  if (status === "EXCELLENT") {
    return "This video provided strong visual evidence for movement analysis.";
  }
  return "This video met the quality requirements for movement analysis.";
}

function friendlyCheckMessage(check: QualityCheck, kind: CheckKind): string {
  const messages: Record<string, string> = {
    format_readable: "Court4 could read the video successfully.",
    landscape_orientation: "Landscape framing helped keep more of the court visible.",
    resolution_passed: "The video resolution supported player visibility.",
    fps_passed: "The frame rate supported movement tracking.",
    duration_passed: "The video was long enough to inspect.",
    upload_preflight_passed: "The video passed the basic quality checks.",
    calibration_available: "Court4 mapped the visible court successfully.",
    selectable_candidates_available: "Court4 found a player with enough visible court evidence.",
    candidate_quality_strong: "The selected player had stable enough tracking evidence.",
    player_visibility_passed: "The selected player was visible on the court often enough.",
    tracked_duration_passed: "Court4 verified enough continuous movement.",
    tracking_continuity_passed: "Player tracking remained continuous.",
    vertical_orientation: "Vertical framing may have left part of the court out of view.",
    resolution_below_minimum: "The video resolution limited dependable player visibility.",
    fps_below_minimum: "The frame rate limited dependable movement tracking.",
    upload_preflight_limited: "The original video quality limits this analysis.",
    candidate_quality_usable: "Player tracking was usable but not consistently strong.",
    tracked_duration_limited: "Only a short section of movement was reliably observed.",
    tracking_gaps_present: "Some parts of the player’s movement were not observed.",
    resolution_too_low: "The video did not provide enough detail to see players reliably.",
    fps_too_low: "The video did not capture movement smoothly enough for reliable tracking.",
    recording_too_short: "Too little continuous gameplay was available to analyze reliably.",
    upload_preflight_blocked: "The video did not meet the minimum quality requirements.",
    calibration_missing: "Court4 could not map the court reliably.",
    no_person_detections: "Court4 could not see players reliably in this video.",
    no_selectable_player_candidate: "No player was visible consistently enough for analysis.",
    player_visibility_too_low: "The selected player was not visible on the court often enough.",
    tracked_duration_too_short: "Court4 could not verify enough continuous movement.",
    tracking_gaps_excessive: "Player tracking was too fragmented for a trustworthy insight.",
    too_many_track_fragments: "The selected player appeared in too many disconnected sections.",
  };
  if (messages[check.code]) {
    return messages[check.code];
  }
  if (kind === "passed") return `${check.label} passed.`;
  if (kind === "warning") return `${check.label} may limit this analysis.`;
  return `${check.label} did not provide enough reliable evidence.`;
}

function friendlyGuidance(guidance: string): string {
  if (guidance.startsWith("Capture a longer")) {
    return "Record a longer continuous section of gameplay.";
  }
  return guidance;
}

function qualityLabel(status: RecordingQualityAssessment["status"]): string {
  if (status === "EXCELLENT") return "Excellent";
  if (status === "GOOD") return "Good";
  if (status === "LIMITED") return "Limited";
  return "Unsuitable";
}
