"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Crosshair,
  Loader2,
  RefreshCw,
  UserCheck,
} from "lucide-react";
import { useRouter } from "next/navigation";
import type { BaseSyntheticEvent, ReactNode } from "react";
import { useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import {
  detectCourt,
  generateAnalytics,
  getPlayerCandidates,
  mergePlayerCandidates,
  rejectPlayerCandidate,
  restorePlayerCandidate,
  selectPlayerCandidate,
  startTracking,
  unmergePlayerCandidate,
} from "@/lib/api/analyses";
import { getArtifactUrl, normalizeApiError } from "@/lib/api/client";
import type {
  AnalysisArtifact,
  AnalysisJob,
  CourtDetectionResponse,
  PlayerCandidate,
  PlayerCandidateCollection,
  TrackingBackend,
  TrackingRequest,
} from "@/lib/api/types";
import { cn } from "@/lib/utils";
import { Button, ButtonLink } from "@/components/ui/button";
import { Skeleton } from "@/components/skeleton";
import { RecordingQualityCard } from "@/components/recording-quality-card";

const trackingFormSchema = z
  .object({
    calibrationId: z.string().min(1, "Select a calibration."),
    backend: z.enum(["ultralytics", "controlled-json"]),
    detectionsJsonl: z.string().trim().optional(),
    frameInterval: z.coerce.number().int().min(1).max(300).optional(),
  })
  .superRefine((values, context) => {
    if (values.backend === "controlled-json" && !values.detectionsJsonl) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: "Controlled JSON tracking needs a detections JSONL artifact path.",
        path: ["detectionsJsonl"],
      });
    }
  });

type TrackingFormValues = z.infer<typeof trackingFormSchema>;

const MIN_TRACKING_ESTIMATE_SECONDS = 60;
const MAX_TRACKING_ESTIMATE_SECONDS = 10 * 60;
const TRACKING_SECONDS_PER_VIDEO_SECOND = 2;

export function MatchWorkflow({ job }: { job: AnalysisJob }) {
  const queryClient = useQueryClient();
  const router = useRouter();
  const trackingRequestInFlight = useRef(false);
  const analysisId = job.analysis_id;
  const calibrationIds = getCalibrationIds(job);
  const defaultCalibrationId = calibrationIds[0] ?? "auto-court-detection";
  const detectionMutation = useMutation({
    mutationFn: () => detectCourt(analysisId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["analysis", analysisId] });
    },
  });
  const candidatesQuery = useQuery({
    queryKey: ["analysis", analysisId, "player-candidates"],
    queryFn: () => getPlayerCandidates(analysisId),
    enabled: job.tracking_completed,
  });
  const trackingMutation = useMutation({
    mutationFn: (request: TrackingRequest) => startTracking(analysisId, request),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["analysis", analysisId] });
      await queryClient.invalidateQueries({
        queryKey: ["analysis", analysisId, "player-candidates"],
      });
    },
    onSettled: () => {
      trackingRequestInFlight.current = false;
    },
  });
  const selectionMutation = useMutation({
    mutationFn: (candidateId: string) => selectPlayerCandidate(analysisId, candidateId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["analysis", analysisId] });
      await queryClient.invalidateQueries({
        queryKey: ["analysis", analysisId, "player-candidates"],
      });
    },
  });
  const rejectionMutation = useMutation({
    mutationFn: (candidateId: string) => rejectPlayerCandidate(analysisId, candidateId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["analysis", analysisId] });
      await queryClient.invalidateQueries({
        queryKey: ["analysis", analysisId, "player-candidates"],
      });
    },
  });
  const mergeMutation = useMutation({
    mutationFn: (candidateIds: [string, string]) =>
      mergePlayerCandidates(analysisId, candidateIds),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["analysis", analysisId, "player-candidates"],
      });
    },
  });
  const restoreMutation = useMutation({
    mutationFn: (candidateId: string) => restorePlayerCandidate(analysisId, candidateId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["analysis", analysisId, "player-candidates"],
      });
    },
  });
  const unmergeMutation = useMutation({
    mutationFn: (candidateId: string) => unmergePlayerCandidate(analysisId, candidateId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["analysis", analysisId] });
      await queryClient.invalidateQueries({
        queryKey: ["analysis", analysisId, "player-candidates"],
      });
    },
  });
  const analyticsMutation = useMutation({
    mutationFn: () => generateAnalytics(analysisId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["analysis", analysisId] });
      router.push(`/matches/${analysisId}/analytics`);
    },
  });
  const trackingForm = useForm<TrackingFormValues>({
    resolver: zodResolver(trackingFormSchema),
    defaultValues: {
      calibrationId: defaultCalibrationId,
      backend: "ultralytics",
      detectionsJsonl: "uploads/detections.jsonl",
      frameInterval: 1,
    },
  });
  const submitTracking = trackingForm.handleSubmit((values) => {
    if (trackingMutation.isPending || trackingRequestInFlight.current) {
      return;
    }

    trackingRequestInFlight.current = true;
    const backend = values.backend as TrackingBackend;
    trackingMutation.mutate({
      calibration_id: values.calibrationId,
      backend,
      detections_jsonl:
        backend === "controlled-json" ? values.detectionsJsonl?.trim() ?? null : null,
      frame_interval: values.frameInterval ?? null,
    });
  });

  return (
    <div className="space-y-6">
      <CourtRecognitionPanel
        job={job}
        result={detectionMutation.data}
        isPending={detectionMutation.isPending}
        error={detectionMutation.error}
        onDetect={() => detectionMutation.mutate()}
      >
        {job.calibration_completed ? (
          <>
            <PlayerTrackingPanel
              analysisId={analysisId}
              job={job}
              calibrationIds={calibrationIds}
              trackingForm={trackingForm}
              submitTracking={submitTracking}
              trackingError={trackingMutation.error}
              isTracking={trackingMutation.isPending}
              candidatesQuery={{
                collection: candidatesQuery.data ?? null,
                isLoading: candidatesQuery.isLoading,
                error: candidatesQuery.error,
                onRetry: () => void candidatesQuery.refetch(),
              }}
              review={{
                pendingCandidateId:
                  selectionMutation.variables ??
                  rejectionMutation.variables ??
                  unmergeMutation.variables ??
                  restoreMutation.variables ??
                  null,
                isPending:
                  selectionMutation.isPending ||
                  rejectionMutation.isPending ||
                  mergeMutation.isPending ||
                  restoreMutation.isPending ||
                  unmergeMutation.isPending,
                error:
                  selectionMutation.error ??
                  rejectionMutation.error ??
                  mergeMutation.error ??
                  restoreMutation.error ??
                  unmergeMutation.error,
                onSelect: (candidateId) => selectionMutation.mutate(candidateId),
                onReject: (candidateId) => rejectionMutation.mutate(candidateId),
                onMerge: (candidateIds) => mergeMutation.mutate(candidateIds),
                onUnmerge: (candidateId) => unmergeMutation.mutate(candidateId),
                onRestore: (candidateId) => restoreMutation.mutate(candidateId),
              }}
              matchIQPanel={
                job.player_selected ? (
                  <MatchIQPanel
                    analysisId={analysisId}
                    analyticsCompleted={job.analytics_completed}
                    isPending={analyticsMutation.isPending}
                    error={analyticsMutation.error}
                    onGenerate={() => analyticsMutation.mutate()}
                  />
                ) : null
              }
            />
          </>
        ) : null}
      </CourtRecognitionPanel>
    </div>
  );
}

function CourtRecognitionPanel({
  job,
  result,
  isPending,
  error,
  onDetect,
  children,
}: {
  job: AnalysisJob;
  result: CourtDetectionResponse | undefined;
  isPending: boolean;
  error: unknown;
  onDetect: () => void;
  children: ReactNode;
}) {
  const artifacts = result?.artifacts.length ? result.artifacts : job.available_artifacts;
  const verification = findArtifact(artifacts, "verification.jpg");
  const detectionStatus = job.court_detection_status ?? result?.status ?? null;
  const detectionConfidence = job.court_detection_confidence ?? result?.confidence ?? null;
  const detectionNeedsManualCalibration =
    detectionStatus === "failed" ||
    detectionStatus === "low_confidence" ||
    (job.manual_calibration_required && !job.calibration_completed);

  return (
    <section
      aria-labelledby="court-recognition-heading"
      className="rounded-md border border-court-line bg-white p-5 shadow-panel"
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-court-green">
            Court setup
          </p>
          <h2
            id="court-recognition-heading"
            className="mt-2 text-lg font-semibold text-court-ink"
          >
            {job.calibration_completed
              ? "Court recognized"
              : isPending
                ? "Recognizing the court"
                : "Recognize the court"}
          </h2>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-court-muted">
            {job.calibration_completed
              ? "We found the court and are ready to measure player movement."
              : "Court4 checks the match video to understand where play happens."}
          </p>
        </div>
        {!job.calibration_completed ? (
          <Button type="button" onClick={onDetect} disabled={isPending}>
            {isPending ? (
              <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" />
            ) : (
              <Crosshair aria-hidden="true" className="h-4 w-4" />
            )}
            {isPending ? "Recognizing" : "Recognize Court"}
          </Button>
        ) : (
          <span className="inline-flex items-center gap-2 rounded-md bg-green-50 px-3 py-2 text-sm font-semibold text-court-green">
            <CheckCircle2 aria-hidden="true" className="h-4 w-4" />
            {detectionStatus === "detected" && detectionConfidence !== null
              ? `${toPercent(detectionConfidence)}% confidence`
              : "Court ready"}
          </span>
        )}
      </div>

      {isPending ? (
        <div className="mt-5" role="status" aria-label="Recognizing court">
          <Skeleton className="h-28" />
        </div>
      ) : null}

      <WorkflowError error={error} onRetry={onDetect} />

      {!job.calibration_completed && result ? (
        <DetectionResultMessage analysisId={job.analysis_id} result={result} />
      ) : null}
      {!job.calibration_completed && !result && detectionStatus ? (
        <PersistedDetectionMessage
          analysisId={job.analysis_id}
          status={detectionStatus}
          confidence={detectionConfidence}
          manualCalibrationRequired={job.manual_calibration_required}
        />
      ) : null}

      {job.calibration_completed ? (
        <div className="mt-5 space-y-5">
          <div className="rounded-md border border-green-200 bg-green-50 p-4">
            {children}
          </div>

          {verification ? (
            <ArtifactPreview
              analysisId={job.analysis_id}
              artifact={verification}
              label="Detected court"
            />
          ) : null}
        </div>
      ) : null}

      {detectionNeedsManualCalibration && !job.calibration_completed && !result && !detectionStatus ? (
        <div className="mt-5 flex flex-wrap items-center justify-between gap-4 rounded-md border border-amber-200 bg-amber-50 p-4">
          <div className="flex gap-3">
            <AlertTriangle aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-court-amber" />
            <div>
              <p className="text-sm font-semibold text-court-ink">
                Court4 could not confidently recognize the court.
              </p>
              <p className="mt-1 text-sm text-court-muted">
                Use manual calibration to mark the outer court corners.
              </p>
            </div>
          </div>
          <ButtonLink href={`/matches/${job.analysis_id}/calibrate`} variant="secondary">
            Calibrate Manually
          </ButtonLink>
        </div>
      ) : null}
    </section>
  );
}

function DetectionResultMessage({
  analysisId,
  result,
}: {
  analysisId: string;
  result: CourtDetectionResponse;
}) {
  if (result.status === "detected") {
    return (
      <div className="mt-5 rounded-md border border-green-200 bg-green-50 p-4">
        <p className="text-sm font-semibold text-court-green">
          Court recognized with {toPercent(result.confidence)}% confidence.
        </p>
        <p className="mt-1 text-sm text-court-muted">Ready to find players.</p>
      </div>
    );
  }

  return (
    <div className="mt-5 rounded-md border border-amber-200 bg-amber-50 p-4">
      <p className="text-sm font-semibold text-court-ink">
        Court4 could not confidently recognize the court.
      </p>
      <p className="mt-1 text-sm text-court-muted">
        Confidence was {toPercent(result.confidence)}%. Manual calibration is required.
      </p>
      <ButtonLink className="mt-4" href={`/matches/${analysisId}/calibrate`} variant="secondary">
        Calibrate Manually
      </ButtonLink>
    </div>
  );
}

function PersistedDetectionMessage({
  analysisId,
  status,
  confidence,
  manualCalibrationRequired,
}: {
  analysisId: string;
  status: NonNullable<AnalysisJob["court_detection_status"]>;
  confidence: number | null;
  manualCalibrationRequired: boolean;
}) {
  if (status === "detected") {
    return (
      <div className="mt-5 rounded-md border border-green-200 bg-green-50 p-4">
        <p className="text-sm font-semibold text-court-green">
          {confidence !== null
            ? `Court recognized with ${toPercent(confidence)}% confidence.`
            : "Court recognized."}
        </p>
        <p className="mt-1 text-sm text-court-muted">Ready to find players.</p>
      </div>
    );
  }

  return (
    <div className="mt-5 rounded-md border border-amber-200 bg-amber-50 p-4">
      <p className="text-sm font-semibold text-court-ink">
        Court4 could not confidently recognize the court.
      </p>
      <p className="mt-1 text-sm text-court-muted">
        {confidence !== null
          ? `Confidence was ${toPercent(confidence)}%. Manual calibration is required.`
          : "Manual calibration is required."}
      </p>
      {manualCalibrationRequired ? (
        <ButtonLink className="mt-4" href={`/matches/${analysisId}/calibrate`} variant="secondary">
          Calibrate Manually
        </ButtonLink>
      ) : null}
    </div>
  );
}

function PlayerTrackingPanel({
  analysisId,
  job,
  calibrationIds,
  trackingForm,
  submitTracking,
  trackingError,
  isTracking,
  candidatesQuery,
  review,
  matchIQPanel,
}: {
  analysisId: string;
  job: AnalysisJob;
  calibrationIds: string[];
  trackingForm: ReturnType<typeof useForm<TrackingFormValues>>;
  submitTracking: (event?: BaseSyntheticEvent) => Promise<void>;
  trackingError: unknown;
  isTracking: boolean;
  candidatesQuery: {
    collection: PlayerCandidateCollection | null;
    isLoading: boolean;
    error: unknown;
    onRetry: () => void;
  };
  review: {
    pendingCandidateId: string | null;
    isPending: boolean;
    error: unknown;
    onSelect: (candidateId: string) => void;
    onReject: (candidateId: string) => void;
    onMerge: (candidateIds: [string, string]) => void;
    onUnmerge: (candidateId: string) => void;
    onRestore: (candidateId: string) => void;
  };
  matchIQPanel: ReactNode;
}) {
  return (
    <section id="player-tracking" aria-labelledby="player-tracking-heading">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-court-green">
            {job.tracking_completed ? "Player selection" : isTracking ? "Player tracking" : "Next step"}
          </p>
          <h2
            id="player-tracking-heading"
            className="mt-2 text-lg font-semibold text-court-ink"
          >
            {job.tracking_completed ? "Choose your player" : isTracking ? "Finding players" : "Find the players"}
          </h2>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-court-muted">
            {job.tracking_completed
              ? "Choose the player that represents you."
              : isTracking
                ? "Court4 is analyzing movement across the match. This may take a few minutes."
                : "We will analyze movement across the match, then choose yourself."}
          </p>
        </div>
        {job.tracking_completed ? (
          <span className="inline-flex items-center gap-2 rounded-md bg-green-50 px-3 py-2 text-sm font-semibold text-court-green">
            <CheckCircle2 aria-hidden="true" className="h-4 w-4" />
            <span className="tabular-nums">100%</span>
            Complete
          </span>
        ) : null}
      </div>

      {!job.tracking_completed ? (
        <form onSubmit={submitTracking} className="mt-5 space-y-4">
          {isTracking ? (
            <TrackingProgress
              sourceDurationSeconds={
                job.upload_preflight?.upload_signals?.duration_seconds ?? null
              }
            />
          ) : (
            <div className="flex flex-wrap items-center gap-3">
              <Button type="submit" disabled={calibrationIds.length === 0}>
                <UserCheck aria-hidden="true" className="h-4 w-4" />
                Find Players
              </Button>
            </div>
          )}

          <FormError message={trackingForm.formState.errors.detectionsJsonl?.message} />
          <WorkflowError
            error={trackingError}
            title="We could not identify the players"
            message="Try the analysis again. If the problem continues, use a clearer video."
            onRetry={() => void submitTracking()}
          />
        </form>
      ) : (
        <PlayerSelectionPanel
          analysisId={analysisId}
          collection={candidatesQuery.collection}
          isLoading={candidatesQuery.isLoading}
          error={candidatesQuery.error}
          pendingCandidateId={review.pendingCandidateId}
          isPending={review.isPending}
          reviewError={review.error}
          onSelect={review.onSelect}
          onReject={review.onReject}
          onMerge={review.onMerge}
          onUnmerge={review.onUnmerge}
          onRestore={review.onRestore}
          onRetry={candidatesQuery.onRetry}
          matchIQPanel={matchIQPanel}
        />
      )}
    </section>
  );
}

function TrackingProgress({
  sourceDurationSeconds,
}: {
  sourceDurationSeconds: number | null;
}) {
  const estimatedSeconds = estimateTrackingSeconds(sourceDurationSeconds);
  const [progress, setProgress] = useState(1);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  useEffect(() => {
    const startedAt = Date.now();

    const updateProgress = () => {
      const elapsed = Math.max(0, (Date.now() - startedAt) / 1000);
      const nextProgress = Math.min(
        99,
        Math.max(1, Math.floor((elapsed / estimatedSeconds) * 98) + 1),
      );
      setElapsedSeconds(Math.floor(elapsed));
      setProgress(nextProgress);
    };

    updateProgress();
    const intervalId = window.setInterval(updateProgress, 500);
    return () => window.clearInterval(intervalId);
  }, [estimatedSeconds]);

  return (
    <div className="rounded-md border border-green-200 bg-white/80 p-4 shadow-sm">
      <div className="flex items-end justify-between gap-4">
        <div>
          <p className="text-sm font-semibold text-court-ink">Analyzing player movement</p>
          <p className="mt-1 text-xs text-court-muted">
            {progress === 99
              ? "Finalizing player tracks."
              : `${formatElapsedTime(elapsedSeconds)} elapsed · ${formatElapsedTime(
                  estimatedSeconds,
                )} estimated total`}
          </p>
        </div>
        <span className="text-2xl font-semibold tabular-nums text-court-green">
          {progress}%
        </span>
      </div>
      <div
        role="progressbar"
        aria-label="Player tracking progress"
        aria-valuemin={1}
        aria-valuemax={100}
        aria-valuenow={progress}
        className="mt-3 h-2.5 overflow-hidden rounded-full bg-green-100"
      >
        <div
          className="h-full rounded-full bg-gradient-to-r from-court-green to-lime-400 transition-[width] duration-500 ease-out"
          style={{ width: `${progress}%` }}
        />
      </div>
    </div>
  );
}

function PlayerSelectionPanel({
  analysisId,
  collection,
  isLoading,
  error,
  pendingCandidateId,
  isPending,
  reviewError,
  onSelect,
  onReject,
  onMerge,
  onUnmerge,
  onRestore,
  onRetry,
  matchIQPanel,
}: {
  analysisId: string;
  collection: PlayerCandidateCollection | null;
  isLoading: boolean;
  error: unknown;
  pendingCandidateId: string | null;
  isPending: boolean;
  reviewError: unknown;
  onSelect: (candidateId: string) => void;
  onReject: (candidateId: string) => void;
  onMerge: (candidateIds: [string, string]) => void;
  onUnmerge: (candidateId: string) => void;
  onRestore: (candidateId: string) => void;
  onRetry: () => void;
  matchIQPanel: ReactNode;
}) {
  const [mergeSourceId, setMergeSourceId] = useState<string | null>(null);
  const [mergeTargetId, setMergeTargetId] = useState<string | null>(null);
  if (isLoading) {
    return <Skeleton className="mt-5 h-64" />;
  }

  if (error) {
    return (
      <WorkflowError
        error={error}
        className="mt-5"
        title="We could not identify the players"
        message="Try the analysis again or open advanced settings to adjust processing options."
        onRetry={onRetry}
      />
    );
  }

  const candidates = (collection?.candidates ?? [])
    .filter((candidate) => candidate.selection_eligible)
    .slice(0, 4);
  const restorableExcludedCandidates =
    collection?.excluded_candidates.filter((candidate) => candidate.selection_eligible) ?? [];
  const playerCards = candidates.map((candidate, index) => ({
    candidate,
    label: `Player ${index + 1}`,
  }));
  const selectedPlayer = playerCards.find(
    (player) => player.candidate.candidate_id === collection?.selected_candidate_id,
  );
  const mergeSource = playerCards.find(
    (player) => player.candidate.candidate_id === mergeSourceId,
  );
  const mergeTarget = playerCards.find(
    (player) => player.candidate.candidate_id === mergeTargetId,
  );

  if (!collection || candidates.length === 0) {
    return (
      <div className="mt-5 rounded-md border border-amber-200 bg-amber-50 p-4">
        <p className="text-sm font-semibold text-court-ink">
          Court4 found people in the video, but none were tracked long enough to analyze reliably.
        </p>
        <p className="mt-1 text-sm text-court-muted">
          Try finding players again with adjusted processing options.
        </p>
        {restorableExcludedCandidates.length ? (
          <details className="mt-4 rounded-md border border-court-line bg-white p-4 text-sm">
            <summary className="cursor-pointer font-semibold text-court-ink">
              Excluded candidates ({restorableExcludedCandidates.length})
            </summary>
            <div className="mt-3 space-y-2">
              {restorableExcludedCandidates.map((candidate, index) => (
                <div
                  key={candidate.candidate_id}
                  className="flex items-center justify-between gap-3"
                >
                  <p>Excluded player {index + 1}</p>
                  <Button
                    type="button"
                    variant="secondary"
                    disabled={isPending}
                    onClick={() => onRestore(candidate.candidate_id)}
                  >
                    Restore
                  </Button>
                </div>
              ))}
            </div>
          </details>
        ) : null}
      </div>
    );
  }

  return (
    <div className="mt-5 space-y-5">
      {selectedPlayer ? (
        <div className="rounded-md border border-green-200 bg-green-50 p-4 text-sm font-semibold text-court-green">
          You selected {selectedPlayer.label}
        </div>
      ) : null}

      <RecordingQualityCard
        assessment={collection.analysis_readiness}
        title="Analysis readiness"
        showRetry={collection.analysis_readiness?.status === "UNSUITABLE"}
      />

      {candidates.every((candidate) => candidate.quality === "UNCERTAIN") ? (
        <div className="rounded-md border border-amber-200 bg-amber-50 p-4 text-sm text-court-muted">
          Court4 found possible players, but they need your review.
        </div>
      ) : null}

      {mergeSource && mergeTarget ? (
        <div className="rounded-md border border-court-line bg-court-panel p-4">
          <p className="font-semibold text-court-ink">
            Confirm that {mergeSource.label} and {mergeTarget.label} are the same player
          </p>
          <p className="mt-1 text-sm text-court-muted">
            Court4 will combine their non-overlapping tracked sections. Inconsistent or
            simultaneous candidates are blocked.
          </p>
          <div className="mt-3 flex gap-3">
            <Button
              type="button"
              disabled={isPending}
              onClick={() => {
                onMerge([
                  mergeSource.candidate.candidate_id,
                  mergeTarget.candidate.candidate_id,
                ]);
                setMergeSourceId(null);
                setMergeTargetId(null);
              }}
            >
              Confirm merge
            </Button>
            <Button
              type="button"
              variant="secondary"
              onClick={() => {
                setMergeSourceId(null);
                setMergeTargetId(null);
              }}
            >
              Cancel
            </Button>
          </div>
        </div>
      ) : null}

      <div
        role="group"
        aria-label="Player choices and Match IQ"
        className="grid items-start gap-4 md:grid-cols-2 xl:grid-cols-3"
      >
        {playerCards.map(({ candidate, label }) => {
          const isSelected = collection.selected_candidate_id === candidate.candidate_id;
          const isCurrentSelectionPending =
            isPending && pendingCandidateId === candidate.candidate_id;
          const previewPath = candidate.representative_crop_artifact;

          return (
            <article
              key={candidate.candidate_id}
              className={cn(
                "rounded-md border p-4 transition",
                isSelected
                  ? "border-green-300 bg-green-50"
                  : "border-court-line bg-white hover:border-court-green",
              )}
            >
              <div className="flex items-start justify-between gap-3">
                <h3 className="text-base font-semibold text-court-ink">{label}</h3>
                <CandidateQualityBadge quality={candidate.quality} />
              </div>

              <div className="mt-4 overflow-hidden rounded-md border border-court-line bg-court-panel">
                {previewPath ? (
                  <div className="aspect-video bg-white">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={getArtifactUrl(analysisId, previewPath)}
                      alt={`${label} reference`}
                      className="h-full w-full object-contain"
                    />
                  </div>
                ) : (
                  <div className="flex aspect-video items-center justify-center px-4 text-center text-sm text-court-muted">
                    Player preview unavailable
                  </div>
                )}
              </div>

              <p className="mt-3 text-sm text-court-muted">
                Tracked for {formatTrackedDuration(candidate.total_observed_duration)} across{" "}
                {candidate.total_observed_frames} observations.
              </p>
              {candidate.court_side_estimate === "NEAR" ||
              candidate.court_side_estimate === "FAR" ? (
                <p className="mt-1 text-sm text-court-muted">
                  Estimated {candidate.court_side_estimate.toLowerCase()} court side
                </p>
              ) : null}
              {candidate.warnings.length ? (
                <p className="mt-2 text-sm text-amber-700">
                  {candidateWarningLabel(candidate.warnings[0])}
                </p>
              ) : null}

              <Button
                className="mt-4 w-full"
                type="button"
                disabled={isPending}
                onClick={() => onSelect(candidate.candidate_id)}
              >
                <UserCheck aria-hidden="true" className="h-4 w-4" />
                {isCurrentSelectionPending ? "Saving" : isSelected ? "Selected" : "This is me"}
              </Button>

              <div className="mt-2 grid grid-cols-2 gap-2">
                <Button
                  type="button"
                  variant="secondary"
                  disabled={isPending}
                  onClick={() => onReject(candidate.candidate_id)}
                >
                  Not a player
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  disabled={isPending || candidates.length < 2}
                  onClick={() => {
                    if (mergeSourceId && mergeSourceId !== candidate.candidate_id) {
                      setMergeTargetId(candidate.candidate_id);
                    } else {
                      setMergeSourceId(candidate.candidate_id);
                      setMergeTargetId(null);
                    }
                  }}
                >
                  {mergeSourceId && mergeSourceId !== candidate.candidate_id
                    ? "Merge with this"
                    : "Same player"}
                </Button>
              </div>

              {candidate.manual_merge_id ? (
                <Button
                  className="mt-2 w-full"
                  type="button"
                  variant="secondary"
                  disabled={isPending}
                  onClick={() => onUnmerge(candidate.candidate_id)}
                >
                  Undo merge
                </Button>
              ) : null}

              <details className="mt-4 rounded-md border border-court-line bg-court-panel p-3">
                <summary className="cursor-pointer text-sm font-semibold text-court-ink">
                  Preview candidate
                </summary>
                <div className="mt-3 grid gap-2">
                  {candidate.preview_frames.map((preview) =>
                    preview.full_frame_artifact ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        key={`${candidate.candidate_id}-${preview.frame_index}`}
                        src={getArtifactUrl(analysisId, preview.full_frame_artifact)}
                        alt={`${label} at ${preview.timestamp_seconds.toFixed(1)} seconds`}
                        className="w-full rounded-md border border-court-line"
                      />
                    ) : null,
                  )}
                </div>
              </details>

            </article>
          );
        })}
        {matchIQPanel}
      </div>

      {restorableExcludedCandidates.length ? (
        <details className="rounded-md border border-court-line bg-white p-4 text-sm">
          <summary className="cursor-pointer font-semibold text-court-ink">
            Excluded candidates ({restorableExcludedCandidates.length})
          </summary>
          <div className="mt-3 space-y-2 text-court-muted">
            {restorableExcludedCandidates.map((candidate, index) => (
              <div key={candidate.candidate_id} className="flex items-center justify-between gap-3">
                <p>
                  Excluded player {index + 1}: {candidate.rejection_reason ?? "not a player"}
                </p>
                <Button
                  type="button"
                  variant="secondary"
                  disabled={isPending}
                  onClick={() => onRestore(candidate.candidate_id)}
                >
                  Restore
                </Button>
              </div>
            ))}
          </div>
        </details>
      ) : null}
      <WorkflowError
        error={reviewError}
        title="Court4 could not save the candidate review"
      />
    </div>
  );
}

function MatchIQPanel({
  analysisId,
  analyticsCompleted,
  isPending,
  error,
  onGenerate,
}: {
  analysisId: string;
  analyticsCompleted: boolean;
  isPending: boolean;
  error: unknown;
  onGenerate: () => void;
}) {
  return (
    <section
      aria-labelledby="match-iq-heading"
      className="rounded-md border border-court-line bg-white p-5 shadow-panel"
    >
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-court-green">
            Your Match IQ
          </p>
          <h2 id="match-iq-heading" className="mt-2 text-lg font-semibold text-court-ink">
            {analyticsCompleted ? "Match IQ is ready" : "Generate your Match IQ"}
          </h2>
          <p className="mt-1 text-sm text-court-muted">
            Court4 will build the movement report from the player you selected.
          </p>
        </div>
        {analyticsCompleted ? (
          <ButtonLink href={`/matches/${analysisId}/analytics`}>
            View Match IQ
            <ArrowRight aria-hidden="true" className="h-4 w-4" />
          </ButtonLink>
        ) : (
          <Button type="button" disabled={isPending} onClick={onGenerate}>
            {isPending ? <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" /> : null}
            {isPending ? "Generating Match IQ" : "Generate My Match IQ"}
          </Button>
        )}
      </div>
      <WorkflowError error={error} title="Court4 could not generate your Match IQ" />
    </section>
  );
}

function ArtifactPreview({
  analysisId,
  artifact,
  label,
}: {
  analysisId: string;
  artifact: AnalysisArtifact;
  label: string;
}) {
  return (
    <figure className="overflow-hidden rounded-md border border-court-line bg-court-panel">
      <div className="aspect-video bg-white">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={getArtifactUrl(analysisId, artifact.path)}
          alt={label}
          className="h-full w-full object-contain"
        />
      </div>
    </figure>
  );
}

function WorkflowError({
  error,
  title,
  message,
  onRetry,
  className,
}: {
  error: unknown;
  title?: string;
  message?: string;
  onRetry?: () => void;
  className?: string;
}) {
  if (!error) {
    return null;
  }

  const normalized = normalizeApiError(error);
  const isBackendUnavailable = normalized.code === "backend_unavailable";
  const isDetectorModelMissing = normalized.code === "detector_model_missing";
  const isImpossibleMerge = normalized.code === "impossible_candidate_merge";
  const visibleTitle = isBackendUnavailable
    ? "Court4 cannot connect to the analysis service"
    : isDetectorModelMissing
      ? "Player detection model is missing"
    : isImpossibleMerge
      ? "These candidates cannot be merged safely"
    : title ?? "Court4 could not complete this step";
  const visibleMessage = isBackendUnavailable
    ? "Make sure the Court4 backend is running, then try again."
    : isDetectorModelMissing
      ? "Player detection is not available because the detector model is missing."
    : isImpossibleMerge
      ? normalized.message
    : message ?? "Try again. If the problem continues, use a clearer video.";

  return (
    <div className={cn("mt-4 rounded-md border border-red-200 bg-red-50 p-4", className)}>
      <p className="text-sm font-semibold text-court-red">{visibleTitle}</p>
      <p className="mt-1 text-sm text-court-red">{visibleMessage}</p>
      {onRetry ? (
        <Button className="mt-4" type="button" variant="secondary" onClick={onRetry}>
          <RefreshCw aria-hidden="true" className="h-4 w-4" />
          Try Again
        </Button>
      ) : null}
    </div>
  );
}

function CandidateQualityBadge({ quality }: { quality: PlayerCandidate["quality"] }) {
  const label = {
    STRONG: "Strong candidate",
    USABLE: "Usable candidate",
    UNCERTAIN: "Needs review",
    REJECTED: "Not enough tracking data",
  }[quality];
  return (
    <span className="rounded-md bg-court-panel px-2 py-1 text-xs font-semibold text-court-ink">
      {label}
    </span>
  );
}

function candidateWarningLabel(reason: string): string {
  const labels: Record<string, string> = {
    short_track_duration: "Only a short tracked section is available.",
    low_in_court_ratio: "Much of this track falls outside the recognized court.",
    high_fragment_count: "This candidate combines several tracked sections.",
    candidate_preview_generation_failure: "Preview images could not be generated.",
    small_subject: "The player appears small in the video.",
    court_side_inconsistent: "Court-side estimates are inconsistent.",
    vertical_video_limitation: "Vertical video may reduce tracking reliability.",
  };
  return labels[reason] ?? "This candidate needs review.";
}

function FormError({ message }: { message?: string }) {
  if (!message) {
    return null;
  }
  return (
    <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-court-red">
      {message}
    </div>
  );
}

function findArtifact(
  artifacts: AnalysisArtifact[],
  filename: string,
): AnalysisArtifact | undefined {
  return artifacts.find((artifact) => artifact.path.endsWith(`/${filename}`));
}

function getCalibrationIds(job: AnalysisJob): string[] {
  const ids = new Set<string>();
  for (const artifact of job.available_artifacts) {
    const match = /^calibrations\/([^/]+)\/calibration\.json$/.exec(artifact.path);
    if (match) {
      ids.add(match[1]);
    }
  }
  return [...ids].sort((first, second) => {
    if (first === "auto-court-detection") {
      return -1;
    }
    if (second === "auto-court-detection") {
      return 1;
    }
    return first.localeCompare(second);
  });
}

function formatTrackedDuration(seconds: number): string {
  if (seconds < 60) {
    return `${seconds.toFixed(1)} sec`;
  }
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = Math.round(seconds % 60);
  return `${minutes} min ${remainingSeconds} sec`;
}

function estimateTrackingSeconds(sourceDurationSeconds: number | null): number {
  const videoDuration = sourceDurationSeconds ?? MIN_TRACKING_ESTIMATE_SECONDS;
  return Math.min(
    MAX_TRACKING_ESTIMATE_SECONDS,
    Math.max(
      MIN_TRACKING_ESTIMATE_SECONDS,
      Math.ceil(videoDuration * TRACKING_SECONDS_PER_VIDEO_SECOND),
    ),
  );
}

function formatElapsedTime(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  return `${minutes}:${remainingSeconds.toString().padStart(2, "0")}`;
}

function toPercent(value: number): number {
  return Math.round(value * 100);
}
