import { AlertCircle, CheckCircle2, Circle, Clock3, XCircle } from "lucide-react";

import type { AnalysisJob } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const stageLabels: Record<string, string> = {
  uploaded: "Match uploaded",
  inspected: "Match uploaded",
  calibrated: "Court recognized",
  tracked: "Players identified",
  player_selected: "Select yourself",
  analyzed: "Your Match IQ",
};

const statusLabels: Record<string, string> = {
  pending: "Waiting",
  processing: "In progress",
  completed: "Complete",
  failed: "Needs attention",
};

type WorkflowStepState = "complete" | "active" | "waiting" | "failed";

export type WorkflowStep = {
  label: string;
  currentLabel: string;
  description: string;
  state: WorkflowStepState;
};

type WorkflowStepDefinition = {
  label: string;
  activeLabel: string;
  complete: boolean;
  descriptions: Record<WorkflowStepState, string>;
};

export function getStageLabel(stage: string): string {
  return stageLabels[stage] ?? humanize(stage);
}

export function getStatusLabel(status: string): string {
  return statusLabels[status] ?? humanize(status);
}

export function getWorkflowSteps(job: AnalysisJob): WorkflowStep[] {
  const definitions: WorkflowStepDefinition[] = [
    {
      label: "Match uploaded",
      activeLabel: "Preparing match",
      complete: job.inspection_completed,
      descriptions: {
        complete: "Your video is ready for Court4.",
        active: "Court4 is preparing your uploaded match.",
        waiting: "Upload your match to begin.",
        failed: "Court4 could not prepare this match.",
      },
    },
    {
      label: "Court recognized",
      activeLabel: "Recognizing court",
      complete: job.calibration_completed,
      descriptions: {
        complete: "The court is ready for player tracking.",
        active: "Court4 is locating the pickleball court.",
        waiting: "Court4 will recognize the court after upload.",
        failed: "Court4 could not recognize the court automatically.",
      },
    },
    {
      label: "Players identified",
      activeLabel: "Finding players",
      complete: job.tracking_completed,
      descriptions: {
        complete: "Player movement has been tracked.",
        active: "Court4 is tracking each player throughout the match.",
        waiting: "Find players after the court is recognized.",
        failed: "We could not identify the players.",
      },
    },
    {
      label: "Select yourself",
      activeLabel: "Select yourself",
      complete: job.player_selected,
      descriptions: {
        complete: "Your player is selected.",
        active: "Choose which player is you.",
        waiting: "Select yourself after players are found.",
        failed: "Court4 could not save your player selection.",
      },
    },
    {
      label: "Your Match IQ",
      activeLabel: "Generate Match IQ",
      complete: job.analytics_completed,
      descriptions: {
        complete: "Match IQ is ready.",
        active: "Generate your Match IQ from your selected player.",
        waiting: "Your Match IQ appears after you select yourself.",
        failed: "Court4 could not generate your Match IQ.",
      },
    },
  ];

  const firstIncompleteIndex = definitions.findIndex((step) => !step.complete);
  const activeIndex = firstIncompleteIndex === -1 ? definitions.length - 1 : firstIncompleteIndex;

  return definitions.map((definition, index) => {
    let state: WorkflowStepState = "waiting";
    if (definition.complete) {
      state = "complete";
    } else if (job.status === "failed" && index === activeIndex) {
      state = "failed";
    } else if (index === activeIndex) {
      state = "active";
    }

    return {
      label: definition.label,
      currentLabel:
        state === "active"
          ? definition.activeLabel
          : state === "failed"
            ? `${definition.label} needs attention`
            : definition.label,
      description: definition.descriptions[state],
      state,
    };
  });
}

export function getCurrentWorkflowStep(job: AnalysisJob): WorkflowStep {
  const steps = getWorkflowSteps(job);
  return (
    steps.find((step) => step.state === "failed") ??
    steps.find((step) => step.state === "active") ??
    steps[steps.length - 1]
  );
}

export function JobStatus({ job }: { job: AnalysisJob }) {
  const steps = getWorkflowSteps(job);
  const currentStep = getCurrentWorkflowStep(job);
  const completeCount = steps.filter((step) => step.state === "complete").length;
  const progress = Math.round((completeCount / steps.length) * 100);

  return (
    <section className="rounded-md border border-court-line bg-white p-5 shadow-panel">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-court-green">
            Match workflow
          </p>
          <h2 className="mt-2 text-lg font-semibold text-court-ink">
            Current step: {currentStep.currentLabel}
          </h2>
          <p className="mt-1 text-sm text-court-muted">{currentStep.description}</p>
        </div>
        <span
          className={cn(
            "inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-semibold",
            currentStep.state === "complete" && "bg-green-50 text-court-green",
            currentStep.state === "failed" && "bg-red-50 text-court-red",
            currentStep.state === "active" && "bg-blue-50 text-court-blue",
            currentStep.state === "waiting" && "bg-court-panel text-court-muted",
          )}
        >
          {currentStep.state === "complete" ? (
            <CheckCircle2 aria-hidden="true" className="h-4 w-4" />
          ) : currentStep.state === "failed" ? (
            <XCircle aria-hidden="true" className="h-4 w-4" />
          ) : (
            <Clock3 aria-hidden="true" className="h-4 w-4" />
          )}
          {currentStep.currentLabel}
        </span>
      </div>

      <div className="mt-5">
        <div className="flex items-center justify-between text-sm text-court-muted">
          <span>{completeCount} of {steps.length} steps complete</span>
          <span>{progress}%</span>
        </div>
        <div
          className="mt-2 h-2 overflow-hidden rounded-full bg-court-panel"
          role="progressbar"
          aria-label="Workflow completion progress"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={progress}
        >
          <div className="h-full rounded-full bg-court-lime" style={{ width: `${progress}%` }} />
        </div>
      </div>

      <ol className="mt-5 grid gap-3 lg:grid-cols-5">
        {steps.map((step) => (
          <li
            key={step.label}
            className={cn(
              "flex min-h-28 gap-3 rounded-md border px-3 py-3 text-sm",
              step.state === "complete" && "border-green-100 bg-green-50 text-court-green",
              step.state === "active" && "border-blue-200 bg-blue-50 text-court-blue shadow-sm",
              step.state === "failed" && "border-red-200 bg-red-50 text-court-red shadow-sm",
              step.state === "waiting" && "border-court-line bg-court-panel text-court-muted",
            )}
          >
            {step.state === "complete" ? (
              <CheckCircle2 aria-hidden="true" className="h-5 w-5 shrink-0" />
            ) : step.state === "active" ? (
              <Clock3 aria-hidden="true" className="h-5 w-5 shrink-0" />
            ) : step.state === "failed" ? (
              <AlertCircle aria-hidden="true" className="h-5 w-5 shrink-0" />
            ) : (
              <Circle aria-hidden="true" className="h-5 w-5 shrink-0" />
            )}
            <span>
              <span className="block font-semibold">{step.label}</span>
              <span className="mt-1 block leading-5">{step.description}</span>
            </span>
          </li>
        ))}
      </ol>

      {job.status === "failed" && job.error ? (
        <details className="mt-5 rounded-md border border-red-200 bg-red-50 p-4 text-sm text-court-red">
          <summary className="cursor-pointer font-semibold">Technical details</summary>
          <p className="mt-2 break-words">{job.error}</p>
        </details>
      ) : null}
    </section>
  );
}

function humanize(value: string): string {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}
