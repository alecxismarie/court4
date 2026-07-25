import { AlertTriangle, CheckCircle2, XCircle } from "lucide-react";
import type { ReactNode } from "react";

import type { RecordingQualityAssessment } from "@/lib/api/types";
import { ButtonLink } from "@/components/ui/button";

export function RecordingQualityCard({
  assessment,
  title,
  showRetry = false,
}: {
  assessment: RecordingQualityAssessment | null;
  title: string;
  showRetry?: boolean;
}) {
  if (!assessment) {
    return (
      <section className="rounded-md border border-court-line bg-white p-5 shadow-panel">
        <h2 className="text-lg font-semibold text-court-ink">{title}</h2>
        <p className="mt-2 text-sm text-court-muted">
          Quality evidence is unavailable for this legacy analysis.
        </p>
      </section>
    );
  }

  const tone =
    assessment.status === "UNSUITABLE"
      ? "border-red-200 bg-red-50 text-court-red"
      : assessment.status === "LIMITED"
        ? "border-amber-200 bg-amber-50 text-amber-800"
        : "border-green-200 bg-green-50 text-court-green";

  return (
    <section className="rounded-md border border-court-line bg-white p-5 shadow-panel">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-court-muted">{title}</p>
          <h2 className="mt-1 text-lg font-semibold text-court-ink">Evidence readiness</h2>
        </div>
        <span className={`rounded-md border px-3 py-1 text-sm font-semibold ${tone}`}>
          {qualityLabel(assessment.status)}
        </span>
      </div>

      <div className="mt-5 grid gap-4 lg:grid-cols-3">
        <QualityList
          title="Passed checks"
          checks={assessment.passed_checks.map((check) => check.message)}
          icon={<CheckCircle2 aria-hidden="true" className="h-4 w-4 text-court-green" />}
          empty="No passed checks recorded."
        />
        <QualityList
          title="Warnings"
          checks={assessment.warnings.map((check) => check.message)}
          icon={<AlertTriangle aria-hidden="true" className="h-4 w-4 text-amber-700" />}
          empty="No warnings."
        />
        <QualityList
          title="Blocking failures"
          checks={assessment.blocking_failures.map((check) => check.message)}
          icon={<XCircle aria-hidden="true" className="h-4 w-4 text-court-red" />}
          empty="No blocking failures."
        />
      </div>

      {assessment.guidance.length > 0 ? (
        <div className="mt-5 rounded-md border border-court-line bg-court-panel p-4">
          <h3 className="text-sm font-semibold text-court-ink">Recording guidance</h3>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-court-muted">
            {assessment.guidance.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
          {showRetry ? (
            <ButtonLink className="mt-4" href="/matches/upload">
              Try another recording
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
  icon,
  empty,
}: {
  title: string;
  checks: string[];
  icon: ReactNode;
  empty: string;
}) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-court-ink">{title}</h3>
      {checks.length > 0 ? (
        <ul className="mt-2 space-y-2 text-sm text-court-muted">
          {checks.map((check) => (
            <li key={check} className="flex items-start gap-2">
              <span className="mt-0.5 shrink-0">{icon}</span>
              <span>{check}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-sm text-court-muted">{empty}</p>
      )}
    </div>
  );
}

function qualityLabel(status: RecordingQualityAssessment["status"]): string {
  if (status === "EXCELLENT") return "Excellent";
  if (status === "GOOD") return "Good";
  if (status === "LIMITED") return "Limited";
  return "Unsuitable";
}
