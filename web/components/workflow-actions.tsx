"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Crosshair,
  Play,
  RefreshCw,
  UserCheck,
} from "lucide-react";
import { useRouter } from "next/navigation";
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
      <CourtDetectionPanel
        job={job}
        result={detectionMutation.data}
        isPending={detectionMutation.isPending}
        error={detectionMutation.error}
        onDetect={() => detectionMutation.mutate()}
      />

      {job.calibration_completed ? (
        <section
          id="player-tracking"
          className="rounded-md border border-court-line bg-white p-5 shadow-panel"
        >
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-sm font-semibold uppercase tracking-wide text-court-green">
                Player Tracking
              </p>
              <h2 className="mt-2 text-lg font-semibold text-court-ink">
                {job.tracking_completed ? "Player tracking complete" : "Start player tracking"}
              </h2>
              <p className="mt-1 text-sm leading-6 text-court-muted">
                Court4 uses the backend tracking service and writes the existing tracking
                artifacts for player selection.
              </p>
            </div>
            {job.tracking_completed ? (
              <span className="inline-flex items-center gap-2 rounded-md bg-green-50 px-3 py-2 text-sm font-semibold text-court-green">
                <CheckCircle2 aria-hidden="true" className="h-4 w-4" />
                Tracked
              </span>
            ) : null}
          </div>

          {!job.tracking_completed ? (
            <form onSubmit={submitTracking} className="mt-5 grid gap-4 lg:grid-cols-4">
              <label className="grid gap-2 text-sm font-medium text-court-ink">
                Calibration
                <select
                  {...trackingForm.register("calibrationId")}
                  className="rounded-md border border-court-line px-3 py-2 text-sm"
                  disabled={calibrationIds.length === 0 || trackingMutation.isPending}
                >
                  {calibrationIds.length === 0 ? (
                    <option value="">No calibration found</option>
                  ) : (
                    calibrationIds.map((calibrationId) => (
                      <option key={calibrationId} value={calibrationId}>
                        {calibrationId}
                      </option>
                    ))
                  )}
                </select>
              </label>
              <label className="grid gap-2 text-sm font-medium text-court-ink">
                Backend
                <select
                  {...trackingForm.register("backend")}
                  className="rounded-md border border-court-line px-3 py-2 text-sm"
                  disabled={trackingMutation.isPending}
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
                    disabled={trackingMutation.isPending}
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
                  disabled={trackingMutation.isPending}
                />
              </label>
              <div className="flex items-end">
                <Button
                  type="submit"
                  disabled={trackingMutation.isPending || calibrationIds.length === 0}
                >
                  <Play aria-hidden="true" className="h-4 w-4" />
                  {trackingMutation.isPending ? "Tracking" : "Start Player Tracking"}
                </Button>
              </div>
              <FormError message={trackingForm.formState.errors.detectionsJsonl?.message} />
              <MutationError error={trackingMutation.error} />
            </form>
          ) : (
            <PlayerSelectionPanel
              analysisId={analysisId}
              tracks={playersQuery.data?.track_summaries ?? []}
              selectedTrackId={playersQuery.data?.selected_player_track_id ?? null}
              artifact={playersQuery.data?.player_selection_artifact ?? null}
              isLoading={playersQuery.isLoading}
              error={playersQuery.error}
              selectingTrackId={selectionMutation.variables ?? null}
              isSelecting={selectionMutation.isPending}
              selectionError={selectionMutation.error}
              onSelect={(trackId) => selectionMutation.mutate(trackId)}
              onRetry={() => void playersQuery.refetch()}
            />
          )}
        </section>
      ) : null}

      {job.player_selected ? (
        <section className="rounded-md border border-court-line bg-white p-5 shadow-panel">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <p className="text-sm font-semibold uppercase tracking-wide text-court-green">
                Analytics
              </p>
              <h2 className="mt-2 text-lg font-semibold text-court-ink">
                {job.analytics_completed ? "Analytics are ready" : "Generate movement analytics"}
              </h2>
              <p className="mt-1 text-sm text-court-muted">
                Analytics use the selected player track and existing backend report generation.
              </p>
            </div>
            {job.analytics_completed ? (
              <ButtonLink href={`/matches/${analysisId}/analytics`}>
                View Analytics
                <ArrowRight aria-hidden="true" className="h-4 w-4" />
              </ButtonLink>
            ) : (
              <Button
                type="button"
                disabled={analyticsMutation.isPending}
                onClick={() => analyticsMutation.mutate()}
              >
                {analyticsMutation.isPending ? "Generating" : "Generate My Analytics"}
              </Button>
            )}
          </div>
          <MutationError error={analyticsMutation.error} />
        </section>
      ) : null}
    </div>
  );
}

function CourtDetectionPanel({
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
  const detectionFailed =
    result?.status === "failed" ||
    result?.status === "low_confidence" ||
    job.manual_calibration_required;

  return (
    <section className="rounded-md border border-court-line bg-white p-5 shadow-panel">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-court-green">
            Court Detection
          </p>
          <h2 className="mt-2 text-lg font-semibold text-court-ink">
            {job.calibration_completed ? "Court calibrated" : "Detect the court"}
          </h2>
          <p className="mt-1 text-sm leading-6 text-court-muted">
            Court4 inspects sampled frames, estimates the four outer corners, and saves the
            existing calibration artifacts only when confidence is high enough.
          </p>
        </div>
        {!job.calibration_completed ? (
          <Button type="button" onClick={onDetect} disabled={isPending}>
            <Crosshair aria-hidden="true" className="h-4 w-4" />
            {isPending ? "Detecting" : "Detect Court"}
          </Button>
        ) : (
          <span className="inline-flex items-center gap-2 rounded-md bg-green-50 px-3 py-2 text-sm font-semibold text-court-green">
            <CheckCircle2 aria-hidden="true" className="h-4 w-4" />
            Calibrated
          </span>
        )}
      </div>

      {isPending ? <Skeleton className="mt-5 h-28" /> : null}
      <MutationError error={error} />

      {result ? (
        <DetectionResultMessage analysisId={job.analysis_id} result={result} />
      ) : null}

      {job.calibration_completed && (verification || topDown) ? (
        <div className="mt-5 grid gap-4 md:grid-cols-2">
          {verification ? (
            <ArtifactPreview
              analysisId={job.analysis_id}
              artifact={verification}
              label="Verification"
            />
          ) : null}
          {topDown ? (
            <ArtifactPreview analysisId={job.analysis_id} artifact={topDown} label="Top-down" />
          ) : null}
        </div>
      ) : null}

      {detectionFailed && !job.calibration_completed && !result ? (
        <div className="mt-5 flex flex-wrap items-center justify-between gap-4 rounded-md border border-amber-200 bg-amber-50 p-4">
          <div className="flex gap-3">
            <AlertTriangle aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-court-amber" />
            <div>
              <p className="text-sm font-semibold text-court-ink">
                Court4 could not confidently detect the court.
              </p>
              <p className="mt-1 text-sm text-court-muted">
                Use manual calibration as the fallback and mark the ordered outer court corners.
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
          Court detected with {(result.confidence * 100).toFixed(0)}% confidence.
        </p>
        <p className="mt-1 text-sm text-court-muted">
          Calibration artifacts were saved. Continue with player tracking below.
        </p>
        <div className="mt-4">
          <ButtonLink href="#player-tracking">
            Continue to Player Tracking
            <ArrowRight aria-hidden="true" className="h-4 w-4" />
          </ButtonLink>
        </div>
      </div>
    );
  }

  return (
    <div className="mt-5 rounded-md border border-amber-200 bg-amber-50 p-4">
      <p className="text-sm font-semibold text-court-ink">
        Detection result: {result.status.replace("_", " ")}
      </p>
      <p className="mt-1 text-sm font-semibold text-court-ink">
        Court4 could not confidently detect the court.
      </p>
      <p className="mt-1 text-sm text-court-muted">
        Confidence was {(result.confidence * 100).toFixed(0)}%. Manual calibration is required.
      </p>
      {result.selected_frame ? (
        <p className="mt-1 break-all text-xs text-court-muted">
          Best sampled frame: {result.selected_frame}
        </p>
      ) : null}
      <ButtonLink className="mt-4" href={`/matches/${analysisId}/calibrate`} variant="secondary">
        Calibrate Manually
      </ButtonLink>
    </div>
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
    const normalized = normalizeApiError(error);
    return (
      <div className="mt-5 rounded-md border border-red-200 bg-red-50 p-4">
        <p className="text-sm text-court-red">{normalized.message}</p>
        <Button className="mt-4" type="button" variant="secondary" onClick={onRetry}>
          <RefreshCw aria-hidden="true" className="h-4 w-4" />
          Retry Players
        </Button>
      </div>
    );
  }

  return (
    <div className="mt-5 space-y-5">
      {artifact ? (
        <ArtifactPreview analysisId={analysisId} artifact={artifact} label="Player selection" />
      ) : null}

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {tracks.map((track) => (
          <article key={track.track_id} className="rounded-md border border-court-line p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h3 className="text-base font-semibold text-court-ink">Track {track.track_id}</h3>
                <p className="mt-1 text-sm text-court-muted">
                  {track.observation_count} observations - {Math.round(track.average_confidence * 100)}%
                  confidence
                </p>
              </div>
              {selectedTrackId === track.track_id ? (
                <span className="rounded-md bg-green-50 px-2 py-1 text-xs font-semibold text-court-green">
                  Selected
                </span>
              ) : null}
            </div>
            <p className="mt-3 text-sm text-court-muted">
              Inside court ratio: {Math.round(track.inside_extended_court_ratio * 100)}%
            </p>
            {track.rejection_reasons.length ? (
              <p className="mt-2 text-xs text-court-red">
                {track.rejection_reasons.join(", ")}
              </p>
            ) : null}
            <Button
              className="mt-4 w-full"
              type="button"
              disabled={!track.eligible_for_selection || isSelecting}
              onClick={() => onSelect(track.track_id)}
            >
              <UserCheck aria-hidden="true" className="h-4 w-4" />
              {isSelecting && selectingTrackId === track.track_id ? "Selecting" : "This is me"}
            </Button>
          </article>
        ))}
      </div>
      <MutationError error={selectionError} />
    </div>
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

function MutationError({ error }: { error: unknown }) {
  if (!error) {
    return null;
  }
  const normalized = normalizeApiError(error);
  return (
    <div className="mt-4 rounded-md border border-red-200 bg-red-50 p-4 text-sm text-court-red">
      {normalized.message}
    </div>
  );
}

function FormError({ message }: { message?: string }) {
  if (!message) {
    return null;
  }
  return (
    <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-court-red lg:col-span-4">
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
