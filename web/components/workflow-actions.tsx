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
  Settings2,
  UserCheck,
} from "lucide-react";
import { useRouter } from "next/navigation";
import type { BaseSyntheticEvent, ReactNode } from "react";
import { useRef } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import {
  detectCourt,
  generateAnalytics,
  getPlayers,
  selectPlayer,
  startTracking,
} from "@/lib/api/analyses";
import { getArtifactUrl, normalizeApiError } from "@/lib/api/client";
import type {
  AnalysisArtifact,
  AnalysisJob,
  CourtDetectionResponse,
  TrackSummary,
  TrackingBackend,
  TrackingRequest,
} from "@/lib/api/types";
import { cn } from "@/lib/utils";
import { Button, ButtonLink } from "@/components/ui/button";
import { Skeleton } from "@/components/skeleton";

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
  const playersQuery = useQuery({
    queryKey: ["analysis", analysisId, "players"],
    queryFn: () => getPlayers(analysisId),
    enabled: job.tracking_completed,
  });
  const trackingMutation = useMutation({
    mutationFn: (request: TrackingRequest) => startTracking(analysisId, request),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["analysis", analysisId] });
      await queryClient.invalidateQueries({ queryKey: ["analysis", analysisId, "players"] });
    },
    onSettled: () => {
      trackingRequestInFlight.current = false;
    },
  });
  const selectionMutation = useMutation({
    mutationFn: (trackId: number) => selectPlayer(analysisId, trackId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["analysis", analysisId] });
      await queryClient.invalidateQueries({ queryKey: ["analysis", analysisId, "players"] });
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
  const trackingBackend = trackingForm.watch("backend");

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
      />

      {job.calibration_completed ? (
        <PlayerTrackingPanel
          analysisId={analysisId}
          job={job}
          calibrationIds={calibrationIds}
          trackingBackend={trackingBackend}
          trackingForm={trackingForm}
          submitTracking={submitTracking}
          trackingError={trackingMutation.error}
          isTracking={trackingMutation.isPending}
          playersQuery={{
            tracks: playersQuery.data?.track_summaries ?? [],
            selectedTrackId: playersQuery.data?.selected_player_track_id ?? null,
            artifact: playersQuery.data?.player_selection_artifact ?? null,
            isLoading: playersQuery.isLoading,
            error: playersQuery.error,
            onRetry: () => void playersQuery.refetch(),
          }}
          selection={{
            selectingTrackId: selectionMutation.variables ?? null,
            isSelecting: selectionMutation.isPending,
            error: selectionMutation.error,
            onSelect: (trackId) => selectionMutation.mutate(trackId),
          }}
        />
      ) : null}

      {job.player_selected ? (
        <MatchIQPanel
          analysisId={analysisId}
          analyticsCompleted={job.analytics_completed}
          isPending={analyticsMutation.isPending}
          error={analyticsMutation.error}
          onGenerate={() => analyticsMutation.mutate()}
        />
      ) : null}
    </div>
  );
}

function CourtRecognitionPanel({
  job,
  result,
  isPending,
  error,
  onDetect,
}: {
  job: AnalysisJob;
  result: CourtDetectionResponse | undefined;
  isPending: boolean;
  error: unknown;
  onDetect: () => void;
}) {
  const artifacts = result?.artifacts.length ? result.artifacts : job.available_artifacts;
  const verification = findArtifact(artifacts, "verification.jpg");
  const topDown = findArtifact(artifacts, "top_down.jpg");
  const detectionStatus = job.court_detection_status ?? result?.status ?? null;
  const detectionConfidence = job.court_detection_confidence ?? result?.confidence ?? null;
  const detectionSelectedFrame =
    job.court_detection_selected_frame ?? result?.selected_frame ?? null;
  const detectionCorners = job.court_detection_detected_corners ?? result?.detected_corners ?? null;
  const detectionNeedsManualCalibration =
    detectionStatus === "failed" ||
    detectionStatus === "low_confidence" ||
    (job.manual_calibration_required && !job.calibration_completed);

  return (
    <section className="rounded-md border border-court-line bg-white p-5 shadow-panel">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-court-green">
            Court recognized
          </p>
          <h2 className="mt-2 text-lg font-semibold text-court-ink">
            {job.calibration_completed
              ? "Court recognized"
              : isPending
                ? "Recognizing the court"
                : "Recognize the court"}
          </h2>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-court-muted">
            {job.calibration_completed
              ? "Court4 found the court and is ready to measure player movement."
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
            Ready to find players
          </span>
        )}
      </div>

      {isPending ? (
        <div className="mt-5" role="status" aria-label="Recognizing court">
          <Skeleton className="h-28" />
        </div>
      ) : null}

      <WorkflowError error={error} onRetry={onDetect} />

      {result ? <DetectionResultMessage analysisId={job.analysis_id} result={result} /> : null}
      {!result && detectionStatus ? (
        <PersistedDetectionMessage
          analysisId={job.analysis_id}
          status={detectionStatus}
          confidence={detectionConfidence}
          manualCalibrationRequired={job.manual_calibration_required}
        />
      ) : null}

      {job.calibration_completed ? (
        <div className="mt-5 space-y-5">
          <div className="grid gap-4 text-sm sm:grid-cols-2">
            {detectionConfidence !== null ? (
              <ResultMetric label="Detection confidence" value={`${toPercent(detectionConfidence)}%`} />
            ) : null}
            <ResultMetric
              label="Readiness"
              value={job.tracking_completed ? "Players identified" : "Ready to find players"}
            />
          </div>

          {verification || topDown ? (
            <div className="grid gap-4 md:grid-cols-2">
              {verification ? (
                <ArtifactPreview
                  analysisId={job.analysis_id}
                  artifact={verification}
                  label="Detected court"
                />
              ) : null}
              {topDown ? (
                <ArtifactPreview
                  analysisId={job.analysis_id}
                  artifact={topDown}
                  label="Top-down court view"
                />
              ) : null}
            </div>
          ) : null}

          <TechnicalDetails>
            <dl className="grid gap-3 text-sm text-court-muted sm:grid-cols-2">
              <DetailItem label="Internal status" value={detectionStatus ?? job.current_stage} />
              <DetailItem label="Calibration source" value={getPrimaryCalibrationId(job, result)} />
              {detectionConfidence !== null ? (
                <DetailItem label="Confidence value" value={detectionConfidence.toFixed(3)} />
              ) : null}
              {detectionSelectedFrame ? (
                <DetailItem label="Selected frame" value={detectionSelectedFrame} />
              ) : null}
              {detectionCorners ? (
                <DetailItem label="Detected corners" value={JSON.stringify(detectionCorners)} />
              ) : null}
            </dl>
          </TechnicalDetails>
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
        <div className="mt-4">
          <ButtonLink href="#player-tracking">
            Continue to Find Players
            <ArrowRight aria-hidden="true" className="h-4 w-4" />
          </ButtonLink>
        </div>
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
      <TechnicalDetails className="mt-4">
        <dl className="grid gap-3 text-sm text-court-muted sm:grid-cols-2">
          <DetailItem label="Internal status" value={result.status} />
          <DetailItem label="Confidence value" value={result.confidence.toFixed(3)} />
          {result.selected_frame ? (
            <DetailItem label="Selected frame" value={result.selected_frame} />
          ) : null}
        </dl>
      </TechnicalDetails>
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
      <TechnicalDetails className="mt-4">
        <dl className="grid gap-3 text-sm text-court-muted sm:grid-cols-2">
          <DetailItem label="Internal status" value={status} />
          {confidence !== null ? (
            <DetailItem label="Confidence value" value={confidence.toFixed(3)} />
          ) : null}
        </dl>
      </TechnicalDetails>
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
  trackingBackend,
  trackingForm,
  submitTracking,
  trackingError,
  isTracking,
  playersQuery,
  selection,
}: {
  analysisId: string;
  job: AnalysisJob;
  calibrationIds: string[];
  trackingBackend: TrackingBackend;
  trackingForm: ReturnType<typeof useForm<TrackingFormValues>>;
  submitTracking: (event?: BaseSyntheticEvent) => Promise<void>;
  trackingError: unknown;
  isTracking: boolean;
  playersQuery: {
    tracks: TrackSummary[];
    selectedTrackId: number | null;
    artifact: AnalysisArtifact | null;
    isLoading: boolean;
    error: unknown;
    onRetry: () => void;
  };
  selection: {
    selectingTrackId: number | null;
    isSelecting: boolean;
    error: unknown;
    onSelect: (trackId: number) => void;
  };
}) {
  return (
    <section id="player-tracking" className="rounded-md border border-court-line bg-white p-5 shadow-panel">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-court-green">
            Players identified
          </p>
          <h2 className="mt-2 text-lg font-semibold text-court-ink">
            {job.tracking_completed ? "Players identified" : isTracking ? "Finding players" : "Find the players"}
          </h2>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-court-muted">
            {job.tracking_completed
              ? "Choose the player that represents you."
              : isTracking
                ? "Court4 is analyzing movement across the match. This may take a few minutes."
                : "Court4 will follow each player throughout the match so you can select yourself."}
          </p>
        </div>
        {job.tracking_completed ? (
          <span className="inline-flex items-center gap-2 rounded-md bg-green-50 px-3 py-2 text-sm font-semibold text-court-green">
            <CheckCircle2 aria-hidden="true" className="h-4 w-4" />
            Players identified
          </span>
        ) : null}
      </div>

      {!job.tracking_completed ? (
        <form onSubmit={submitTracking} className="mt-5 space-y-4">
          <AdvancedSettings
            calibrationIds={calibrationIds}
            isTracking={isTracking}
            trackingBackend={trackingBackend}
            trackingForm={trackingForm}
          />

          <div className="flex flex-wrap items-center gap-3">
            <Button type="submit" disabled={isTracking || calibrationIds.length === 0}>
              {isTracking ? (
                <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" />
              ) : (
                <UserCheck aria-hidden="true" className="h-4 w-4" />
              )}
              {isTracking ? "Finding players" : "Find Players"}
            </Button>
            {isTracking ? (
              <span className="text-sm text-court-muted" role="status">
                Tracking player movement now.
              </span>
            ) : null}
          </div>

          <FormError message={trackingForm.formState.errors.detectionsJsonl?.message} />
          <WorkflowError
            error={trackingError}
            title="We could not identify the players"
            message="Try the analysis again or open advanced settings to adjust processing options."
            onRetry={() => void submitTracking()}
          />
        </form>
      ) : (
        <PlayerSelectionPanel
          analysisId={analysisId}
          tracks={playersQuery.tracks}
          selectedTrackId={playersQuery.selectedTrackId}
          artifact={playersQuery.artifact}
          isLoading={playersQuery.isLoading}
          error={playersQuery.error}
          selectingTrackId={selection.selectingTrackId}
          isSelecting={selection.isSelecting}
          selectionError={selection.error}
          onSelect={selection.onSelect}
          onRetry={playersQuery.onRetry}
        />
      )}
    </section>
  );
}

function AdvancedSettings({
  calibrationIds,
  isTracking,
  trackingBackend,
  trackingForm,
}: {
  calibrationIds: string[];
  isTracking: boolean;
  trackingBackend: TrackingBackend;
  trackingForm: ReturnType<typeof useForm<TrackingFormValues>>;
}) {
  return (
    <details className="rounded-md border border-court-line bg-court-panel p-4">
      <summary className="flex cursor-pointer items-center gap-2 text-sm font-semibold text-court-ink">
        <Settings2 aria-hidden="true" className="h-4 w-4" />
        Advanced settings
      </summary>
      <div className="mt-4 grid gap-4 lg:grid-cols-4">
        <label className="grid gap-2 text-sm font-medium text-court-ink">
          Calibration source
          <select
            {...trackingForm.register("calibrationId")}
            className="rounded-md border border-court-line px-3 py-2 text-sm"
            disabled={calibrationIds.length === 0 || isTracking}
          >
            {calibrationIds.length === 0 ? (
              <option value="">No calibration found</option>
            ) : (
              calibrationIds.map((calibrationId) => (
                <option key={calibrationId} value={calibrationId}>
                  {displayCalibrationSource(calibrationId)}
                </option>
              ))
            )}
          </select>
        </label>
        <label className="grid gap-2 text-sm font-medium text-court-ink">
          Detector backend
          <select
            {...trackingForm.register("backend")}
            className="rounded-md border border-court-line px-3 py-2 text-sm"
            disabled={isTracking}
          >
            <option value="ultralytics">Ultralytics detector</option>
            <option value="controlled-json">Controlled JSON</option>
          </select>
        </label>
        {trackingBackend === "controlled-json" ? (
          <label className="grid gap-2 text-sm font-medium text-court-ink lg:col-span-2">
            Detections JSONL artifact
            <input
              {...trackingForm.register("detectionsJsonl")}
              className="rounded-md border border-court-line px-3 py-2 text-sm"
              placeholder="uploads/detections.jsonl"
              disabled={isTracking}
            />
          </label>
        ) : null}
        <label className="grid gap-2 text-sm font-medium text-court-ink">
          Frame interval
          <input
            {...trackingForm.register("frameInterval")}
            type="number"
            min={1}
            className="rounded-md border border-court-line px-3 py-2 text-sm"
            disabled={isTracking}
          />
        </label>
      </div>
    </details>
  );
}

function PlayerSelectionPanel({
  analysisId,
  tracks,
  selectedTrackId,
  artifact,
  isLoading,
  error,
  selectingTrackId,
  isSelecting,
  selectionError,
  onSelect,
  onRetry,
}: {
  analysisId: string;
  tracks: TrackSummary[];
  selectedTrackId: number | null;
  artifact: AnalysisArtifact | null;
  isLoading: boolean;
  error: unknown;
  selectingTrackId: number | null;
  isSelecting: boolean;
  selectionError: unknown;
  onSelect: (trackId: number) => void;
  onRetry: () => void;
}) {
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

  const eligibleTracks = tracks
    .filter((track) => track.eligible_for_selection)
    .sort(compareTrackSelectionPriority);
  const playerCards = eligibleTracks.map((track, index) => ({
    track,
    label: `Player ${index + 1}`,
  }));
  const selectedPlayer = playerCards.find((player) => player.track.track_id === selectedTrackId);
  const cardsMissingPreviews = playerCards.filter(({ track }) => !track.preview_image).length;

  if (eligibleTracks.length === 0) {
    return (
      <div className="mt-5 rounded-md border border-amber-200 bg-amber-50 p-4">
        <p className="text-sm font-semibold text-court-ink">No selectable players were found.</p>
        <p className="mt-1 text-sm text-court-muted">
          Try finding players again with adjusted processing options.
        </p>
        <TechnicalDetails className="mt-4">
          <TrackDetails tracks={tracks} />
        </TechnicalDetails>
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

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {playerCards.map(({ track, label }) => {
          const isSelected = selectedTrackId === track.track_id;
          const isCurrentSelectionPending = isSelecting && selectingTrackId === track.track_id;
          const previewPath = track.preview_image ?? null;

          return (
            <article
              key={track.track_id}
              className={cn(
                "rounded-md border p-4 transition",
                isSelected
                  ? "border-green-300 bg-green-50"
                  : "border-court-line bg-white hover:border-court-green",
              )}
            >
              <div className="flex items-start justify-between gap-3">
                <h3 className="text-base font-semibold text-court-ink">{label}</h3>
                {isSelected ? (
                  <span className="rounded-md bg-white px-2 py-1 text-xs font-semibold text-court-green">
                    Selected
                  </span>
                ) : null}
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
                Tracked for {formatTrackedDuration(track.duration_seconds)} across{" "}
                {track.observation_count} observations.
              </p>

              <Button
                className="mt-4 w-full"
                type="button"
                disabled={isSelecting}
                onClick={() => onSelect(track.track_id)}
              >
                <UserCheck aria-hidden="true" className="h-4 w-4" />
                {isCurrentSelectionPending ? "Selecting" : "This is me"}
              </Button>

              <TechnicalDetails className="mt-4">
                <TrackDetails tracks={[track]} />
              </TechnicalDetails>
            </article>
          );
        })}
      </div>

      {artifact && cardsMissingPreviews > 0 ? (
        <details className="rounded-md border border-court-line bg-white p-4 text-sm">
          <summary className="cursor-pointer font-semibold text-court-ink">
            Player reference sheet
          </summary>
          <div className="mt-4 overflow-auto rounded-md border border-court-line bg-white p-3">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={getArtifactUrl(analysisId, artifact.path)}
              alt="Player reference sheet"
              className="mx-auto max-h-[520px] max-w-full object-contain"
            />
          </div>
        </details>
      ) : null}
      <WorkflowError error={selectionError} title="Court4 could not save your selection" />
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
    <section className="rounded-md border border-court-line bg-white p-5 shadow-panel">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-court-green">
            Your Match IQ
          </p>
          <h2 className="mt-2 text-lg font-semibold text-court-ink">
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
      <figcaption className="border-t border-court-line px-3 py-2 text-sm font-medium text-court-ink">
        {label}
      </figcaption>
    </figure>
  );
}

function ResultMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="border-l-4 border-court-green pl-3">
      <p className="text-xs font-semibold uppercase tracking-wide text-court-muted">{label}</p>
      <p className="mt-1 text-lg font-semibold text-court-ink">{value}</p>
    </div>
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
  const visibleTitle = isBackendUnavailable
    ? "Court4 cannot connect to the analysis service"
    : isDetectorModelMissing
      ? "Player detection model is missing"
    : title ?? "Court4 could not complete this step";
  const visibleMessage = isBackendUnavailable
    ? "Make sure the Court4 backend is running, then try again."
    : isDetectorModelMissing
      ? "Player detection is not available because the detector model is missing."
    : message ?? "Try again, or open technical details for more information.";

  return (
    <div className={cn("mt-4 rounded-md border border-red-200 bg-red-50 p-4", className)}>
      <p className="text-sm font-semibold text-court-red">{visibleTitle}</p>
      <p className="mt-1 text-sm text-court-red">{visibleMessage}</p>
      <TechnicalDetails className="mt-4">
        <dl className="grid gap-3 text-sm text-court-red sm:grid-cols-2">
          <DetailItem label="Code" value={normalized.code} />
          {normalized.status ? <DetailItem label="Status" value={String(normalized.status)} /> : null}
          <DetailItem label="Message" value={normalized.message} />
        </dl>
      </TechnicalDetails>
      {onRetry ? (
        <Button className="mt-4" type="button" variant="secondary" onClick={onRetry}>
          <RefreshCw aria-hidden="true" className="h-4 w-4" />
          Try Again
        </Button>
      ) : null}
    </div>
  );
}

function TechnicalDetails({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <details className={cn("text-sm", className)}>
      <summary className="cursor-pointer font-semibold text-court-ink">Technical details</summary>
      <div className="mt-3">{children}</div>
    </details>
  );
}

function DetailItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="font-semibold text-court-ink">{label}</dt>
      <dd className="mt-1 break-words">{value}</dd>
    </div>
  );
}

function TrackDetails({ tracks }: { tracks: TrackSummary[] }) {
  return (
    <dl className="grid gap-3 text-sm text-court-muted">
      {tracks.map((track) => (
        <div key={track.track_id} className="grid gap-1">
          <DetailItem label="Observations" value={String(track.observation_count)} />
          <DetailItem label="Court movement" value={formatFeet(track.court_distance_feet ?? 0)} />
          <DetailItem
            label="Court movement rate"
            value={`${(track.court_movement_rate_feet_per_second ?? 0).toFixed(2)} ft/sec`}
          />
          <DetailItem label="Average confidence" value={`${toPercent(track.average_confidence)}%`} />
          <DetailItem
            label="Inside detected court"
            value={`${toPercent(getInsideCourtRatio(track))}%`}
          />
          <DetailItem
            label="Inside extended court"
            value={`${toPercent(track.inside_extended_court_ratio)}%`}
          />
          {track.rejection_reasons.length ? (
            <DetailItem label="Rejection reasons" value={track.rejection_reasons.join(", ")} />
          ) : null}
        </div>
      ))}
    </dl>
  );
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

function getPrimaryCalibrationId(
  job: AnalysisJob,
  result?: CourtDetectionResponse,
): string {
  return result?.calibration?.calibration_id ?? getCalibrationIds(job)[0] ?? "Unavailable";
}

function displayCalibrationSource(value: string): string {
  if (value === "auto-court-detection") {
    return "Automatic court recognition";
  }
  return value;
}

function compareTrackSelectionPriority(first: TrackSummary, second: TrackSummary): number {
  return (
    (second.court_distance_feet ?? 0) - (first.court_distance_feet ?? 0) ||
    second.duration_seconds - first.duration_seconds ||
    second.observation_count - first.observation_count ||
    second.average_confidence - first.average_confidence ||
    first.track_id - second.track_id
  );
}

function formatTrackedDuration(seconds: number): string {
  if (seconds < 60) {
    return `${seconds.toFixed(1)} sec`;
  }
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = Math.round(seconds % 60);
  return `${minutes} min ${remainingSeconds} sec`;
}

function formatFeet(value: number): string {
  return `${value.toFixed(1)} ft`;
}

function getInsideCourtRatio(track: TrackSummary): number {
  if (track.observation_count === 0) {
    return 0;
  }
  return track.court_observation_count / track.observation_count;
}

function toPercent(value: number): number {
  return Math.round(value * 100);
}
