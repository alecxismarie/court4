import { CheckCircle2, Circle, Clock, XCircle } from "lucide-react";

import type { AnalysisJob } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const stageLabels: Record<string, string> = {
  uploaded: "Video uploaded",
  inspected: "Video inspected",
  calibrated: "Court calibrated",
  tracked: "Players tracked",
  player_selected: "Player selected",
  analyzed: "Analysis complete",
};

const statusLabels: Record<string, string> = {
  pending: "Pending",
  processing: "Processing",
  completed: "Completed",
  failed: "Failed",
};

export function getStageLabel(stage: string): string {
  return stageLabels[stage] ?? humanize(stage);
}

export function getStatusLabel(status: string): string {
  return statusLabels[status] ?? humanize(status);
}

export function JobStatus({ job }: { job: AnalysisJob }) {
  const steps = [
    {
      label: "Video uploaded and inspected",
      complete: job.inspection_completed,
      active: !job.inspection_completed,
    },
    {
      label: "Court calibration",
      complete: job.calibration_completed,
      active: job.inspection_completed && !job.calibration_completed,
    },
    {
      label: "Player tracking",
      complete: job.tracking_completed,
      active: job.calibration_completed && !job.tracking_completed,
    },
    {
      label: "Player selection",
      complete: job.player_selected,
      active: job.tracking_completed && !job.player_selected,
    },
    {
      label: "Analytics",
      complete: job.analytics_completed,
      active: job.player_selected && !job.analytics_completed,
    },
  ];

  return (
    <section className="rounded-md border border-court-line bg-white p-5 shadow-panel">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-court-ink">Workflow status</h2>
          <p className="text-sm text-court-muted">{getStageLabel(job.current_stage)}</p>
        </div>
        <span
          className={cn(
            "inline-flex items-center rounded-md px-3 py-1 text-sm font-semibold",
            job.status === "completed" && "bg-green-50 text-court-green",
            job.status === "failed" && "bg-red-50 text-court-red",
            job.status !== "completed" && job.status !== "failed" && "bg-blue-50 text-court-blue",
          )}
        >
          {getStatusLabel(job.status)}
        </span>
      </div>

      <ol className="mt-5 grid gap-3">
        {steps.map((step) => (
          <li
            key={step.label}
            className={cn(
              "flex items-center gap-3 rounded-md border px-3 py-3 text-sm",
              step.complete && "border-green-200 bg-green-50 text-court-green",
              step.active && "border-blue-200 bg-blue-50 text-court-blue",
              !step.complete && !step.active && "border-court-line bg-court-panel text-court-muted",
            )}
          >
            {step.complete ? (
              <CheckCircle2 aria-hidden="true" className="h-5 w-5 shrink-0" />
            ) : step.active ? (
              <Clock aria-hidden="true" className="h-5 w-5 shrink-0" />
            ) : (
              <Circle aria-hidden="true" className="h-5 w-5 shrink-0" />
            )}
            <span>{step.label}</span>
          </li>
        ))}
      </ol>

      {job.status === "failed" && job.error ? (
        <div className="mt-5 flex gap-3 rounded-md border border-red-200 bg-red-50 p-4 text-sm text-court-red">
          <XCircle aria-hidden="true" className="h-5 w-5 shrink-0" />
          <p>{job.error}</p>
        </div>
      ) : null}
    </section>
  );
}

function humanize(value: string): string {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}
