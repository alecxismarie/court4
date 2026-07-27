"use client";

import { RefreshCw } from "lucide-react";
import { useQuery } from "@tanstack/react-query";

import { getAnalysis, getAnalysisFrames } from "@/lib/api/analyses";
import { normalizeApiError } from "@/lib/api/client";
import type { AnalysisJob } from "@/lib/api/types";
import { formatDateTime } from "@/lib/utils";
import { JobStatus, getCurrentWorkflowStep, getStageLabel } from "@/components/job-status";
import { SampledFrames } from "@/components/sampled-frames";
import { Skeleton } from "@/components/skeleton";
import { Button, ButtonLink } from "@/components/ui/button";
import { MatchWorkflow } from "@/components/workflow-actions";
import { RecordingQualityCard } from "@/components/recording-quality-card";

export function MatchDetails({ analysisId }: { analysisId: string }) {
  const jobQuery = useQuery({
    queryKey: ["analysis", analysisId],
    queryFn: () => getAnalysis(analysisId),
  });

  const framesQuery = useQuery({
    queryKey: ["analysis", analysisId, "frames"],
    queryFn: () => getAnalysisFrames(analysisId),
    enabled: jobQuery.data?.inspection_completed === true,
  });

  if (jobQuery.isLoading) {
    return <MatchDetailsSkeleton />;
  }

  if (jobQuery.isError || !jobQuery.data) {
    const error = normalizeApiError(jobQuery.error);
    const isBackendUnavailable = error.code === "backend_unavailable";
    return (
      <div className="rounded-md border border-red-200 bg-red-50 p-6">
        <h1 className="text-xl font-semibold text-court-red">
          {isBackendUnavailable
            ? "Court4 cannot connect to the analysis service"
            : "Match could not be loaded"}
        </h1>
        <p className="mt-2 text-sm text-court-red">
          {isBackendUnavailable
            ? "Make sure the Court4 backend is running, then try again."
            : error.message}
        </p>
        <Button className="mt-5" type="button" variant="secondary" onClick={() => void jobQuery.refetch()}>
          <RefreshCw aria-hidden="true" className="h-4 w-4" />
          Try Again
        </Button>
      </div>
    );
  }

  const job = jobQuery.data;
  const frames = framesQuery.data?.frames ?? [];
  const currentStep = getCurrentWorkflowStep(job);

  return (
    <div className="space-y-6">
      <section className="rounded-md border border-court-line bg-white p-6 shadow-panel">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="text-sm font-semibold uppercase tracking-wide text-court-green">
              Match details
            </p>
            <h1 className="mt-2 text-2xl font-semibold text-court-ink md:text-3xl">
              Video review
            </h1>
            <p className="mt-2 text-sm text-court-muted">
              Current step: {currentStep.currentLabel}
            </p>
          </div>
          <NextAction job={job} />
        </div>

        <dl className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <MetaItem label="Created" value={formatDateTime(job.created_at)} />
          <MetaItem label="Updated" value={formatDateTime(job.updated_at)} />
          <MetaItem label="Workflow stage" value={getStageLabel(job.current_stage)} />
        </dl>
      </section>

      <JobStatus job={job} />

      <RecordingQualityCard
        assessment={job.analysis_readiness ?? job.upload_preflight}
        title={job.analysis_readiness ? "Analysis readiness" : "Video check"}
        showRetry={
          job.analysis_readiness?.status === "UNSUITABLE" ||
          job.upload_preflight?.status === "UNSUITABLE"
        }
      />

      {framesQuery.isError ? (
        <div className="rounded-md border border-red-200 bg-red-50 p-5 text-sm text-court-red">
          <p>{normalizeApiError(framesQuery.error).message}</p>
          <Button
            className="mt-4"
            type="button"
            variant="secondary"
            onClick={() => void framesQuery.refetch()}
          >
            <RefreshCw aria-hidden="true" className="h-4 w-4" />
            Retry frames
          </Button>
        </div>
      ) : (
        <SampledFrames
          analysisId={job.analysis_id}
          frames={frames}
          isLoading={framesQuery.isLoading || framesQuery.isFetching}
        />
      )}

      {job.inspection_completed ? <MatchWorkflow job={job} /> : null}
    </div>
  );
}

function NextAction({ job }: { job: AnalysisJob }) {
  if (job.status === "failed") {
    return (
      <span className="rounded-md bg-red-50 px-3 py-2 text-sm font-semibold text-court-red">
        Review issue
      </span>
    );
  }
  if (job.inspection_completed && !job.calibration_completed) {
    return (
      <span className="rounded-md bg-blue-50 px-3 py-2 text-sm font-semibold text-court-blue">
        Court recognition
      </span>
    );
  }
  if (job.calibration_completed && !job.tracking_completed) {
    return (
      <span className="rounded-md bg-blue-50 px-3 py-2 text-sm font-semibold text-court-blue">
        Find players
      </span>
    );
  }
  if (job.tracking_completed && !job.player_selected) {
    return (
      <span className="rounded-md bg-blue-50 px-3 py-2 text-sm font-semibold text-court-blue">
        Select yourself
      </span>
    );
  }
  if (job.player_selected && !job.analytics_completed) {
    return (
      <span className="rounded-md bg-blue-50 px-3 py-2 text-sm font-semibold text-court-blue">
        Generate Match IQ
      </span>
    );
  }
  if (job.analytics_completed) {
    return <ButtonLink href={`/matches/${job.analysis_id}/analytics`}>View Match IQ</ButtonLink>;
  }
  return (
    <span className="rounded-md bg-court-panel px-3 py-2 text-sm font-semibold text-court-muted">
      {getStageLabel(job.current_stage)}
    </span>
  );
}

function MetaItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-court-line bg-court-panel p-3">
      <dt className="text-xs font-semibold uppercase tracking-wide text-court-muted">{label}</dt>
      <dd className="mt-1 break-words text-sm font-medium text-court-ink">{value}</dd>
    </div>
  );
}

function MatchDetailsSkeleton() {
  return (
    <div className="space-y-6" role="status" aria-label="Loading match details">
      <section className="rounded-md border border-court-line bg-white p-6 shadow-panel">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="mt-4 h-9 w-2/3" />
        <Skeleton className="mt-4 h-4 w-48" />
      </section>
      <Skeleton className="h-72" />
      <Skeleton className="h-64" />
    </div>
  );
}
