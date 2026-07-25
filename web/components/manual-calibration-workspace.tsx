"use client";

import { ArrowLeft, CheckCircle2, RotateCcw, Undo2 } from "lucide-react";
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { getAnalysisFrames, submitCalibration } from "@/lib/api/analyses";
import { getArtifactUrl, normalizeApiError } from "@/lib/api/client";
import type { AnalysisArtifact, CalibrationRequest, SampledFrame } from "@/lib/api/types";
import { cn } from "@/lib/utils";
import { Button, ButtonLink } from "@/components/ui/button";
import { Skeleton } from "@/components/skeleton";

type CornerId = "far_left" | "far_right" | "near_right" | "near_left";

type CalibrationPoint = {
  id: CornerId;
  label: string;
  x: number;
  y: number;
};

type ImageSize = {
  width: number;
  height: number;
};

const CALIBRATION_ID = "manual-calibration";
const MIN_POLYGON_AREA_PIXELS = 1000;
const DISTINCT_POINT_DISTANCE_PIXELS = 3;

const CORNER_STEPS: Array<{ id: CornerId; label: string; hint: string }> = [
  { id: "far_left", label: "Far left", hint: "The far-left outer court corner." },
  { id: "far_right", label: "Far right", hint: "The far-right outer court corner." },
  { id: "near_right", label: "Near right", hint: "The near-right outer court corner." },
  { id: "near_left", label: "Near left", hint: "The near-left outer court corner." },
];

export function ManualCalibrationWorkspace({ analysisId }: { analysisId: string }) {
  const queryClient = useQueryClient();
  const framesQuery = useQuery({
    queryKey: ["analysis", analysisId, "frames"],
    queryFn: () => getAnalysisFrames(analysisId),
  });
  const frames = framesQuery.data?.frames ?? [];
  const [selectedFramePath, setSelectedFramePath] = useState<string | null>(null);
  const selectedFrame = selectFrame(frames, selectedFramePath);
  const [imageSize, setImageSize] = useState<ImageSize | null>(null);
  const [points, setPoints] = useState<CalibrationPoint[]>([]);
  const [submittedArtifacts, setSubmittedArtifacts] = useState<AnalysisArtifact[]>([]);
  const nextStep = CORNER_STEPS[points.length] ?? null;
  const validation = useMemo(
    () => validateCalibration(points, imageSize),
    [imageSize, points],
  );

  const calibrationMutation = useMutation({
    mutationFn: (request: CalibrationRequest) => submitCalibration(analysisId, request),
    onSuccess: async (response) => {
      setSubmittedArtifacts(response.artifacts);
      await queryClient.invalidateQueries({ queryKey: ["analysis", analysisId] });
      await queryClient.invalidateQueries({ queryKey: ["analysis", analysisId, "frames"] });
    },
  });

  function handleImageLoad(event: React.SyntheticEvent<HTMLImageElement>) {
    const image = event.currentTarget;
    if (image.naturalWidth > 0 && image.naturalHeight > 0) {
      setImageSize({ width: image.naturalWidth, height: image.naturalHeight });
    }
  }

  function handleImageClick(event: React.MouseEvent<HTMLImageElement>) {
    if (!nextStep || !imageSize || calibrationMutation.isPending) {
      return;
    }
    const rect = event.currentTarget.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) {
      return;
    }
    const x = ((event.clientX - rect.left) / rect.width) * imageSize.width;
    const y = ((event.clientY - rect.top) / rect.height) * imageSize.height;
    if (!isInsideImage({ x, y }, imageSize)) {
      return;
    }
    setPoints((current) => [
      ...current,
      {
        id: nextStep.id,
        label: nextStep.label,
        x,
        y,
      },
    ]);
    setSubmittedArtifacts([]);
  }

  function resetPoints() {
    if (calibrationMutation.isPending) {
      return;
    }
    setPoints([]);
    setSubmittedArtifacts([]);
  }

  function undoPoint() {
    if (calibrationMutation.isPending) {
      return;
    }
    setPoints((current) => current.slice(0, -1));
    setSubmittedArtifacts([]);
  }

  function submitManualCalibration() {
    if (!selectedFrame || !validation.valid || calibrationMutation.isPending) {
      return;
    }
    const byId = Object.fromEntries(points.map((point) => [point.id, point])) as Record<
      CornerId,
      CalibrationPoint
    >;
    calibrationMutation.mutate({
      calibration_id: CALIBRATION_ID,
      source_frame: selectedFrame.path,
      near_left: toRequestPoint(byId.near_left),
      near_right: toRequestPoint(byId.near_right),
      far_right: toRequestPoint(byId.far_right),
      far_left: toRequestPoint(byId.far_left),
    });
  }

  if (framesQuery.isLoading) {
    return (
      <div className="space-y-6" role="status" aria-label="Loading manual calibration">
        <Skeleton className="h-32" />
        <Skeleton className="h-[520px]" />
      </div>
    );
  }

  if (framesQuery.isError) {
    const error = normalizeApiError(framesQuery.error);
    return (
      <div className="rounded-md border border-red-200 bg-red-50 p-6">
        <h1 className="text-xl font-semibold text-court-red">Calibration frames could not be loaded</h1>
        <p className="mt-2 text-sm text-court-red">{error.message}</p>
      </div>
    );
  }

  if (!selectedFrame) {
    return (
      <div className="rounded-md border border-amber-200 bg-amber-50 p-6">
        <h1 className="text-xl font-semibold text-court-ink">No sampled frames are available</h1>
        <p className="mt-2 text-sm text-court-muted">
          Upload inspection must finish before manual calibration can begin.
        </p>
        <ButtonLink className="mt-5" href={`/matches/${analysisId}`} variant="secondary">
          <ArrowLeft aria-hidden="true" className="h-4 w-4" />
          Back to Match
        </ButtonLink>
      </div>
    );
  }

  const verification = findArtifact(submittedArtifacts, "verification.jpg");
  const topDown = findArtifact(submittedArtifacts, "top_down.jpg");

  return (
    <div className="space-y-6">
      <section className="rounded-md border border-court-line bg-white p-6 shadow-panel">
        <p className="text-sm font-semibold uppercase tracking-wide text-court-green">
          Manual court calibration
        </p>
        <h1 className="mt-2 text-3xl font-semibold text-court-ink">Mark the court corners</h1>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-court-muted">
          Select a clear sampled frame, then mark the four outer court corners in this order:
          far left, far right, near right, near left.
        </p>
      </section>

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="rounded-md border border-court-line bg-white p-4 shadow-panel">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <label className="grid min-w-[16rem] gap-2 text-sm font-semibold text-court-ink">
              Calibration frame
              <select
                className="rounded-md border border-court-line px-3 py-2 text-sm"
                value={selectedFrame.path}
                onChange={(event) => {
                  setSelectedFramePath(event.target.value);
                  setPoints([]);
                  setImageSize(null);
                  setSubmittedArtifacts([]);
                }}
                disabled={calibrationMutation.isPending}
              >
                {frames.map((frame) => (
                  <option key={frame.path} value={frame.path}>
                    {frame.path.split("/").at(-1) ?? frame.path}
                  </option>
                ))}
              </select>
            </label>
            <div className="flex flex-wrap gap-2">
              <Button type="button" variant="secondary" onClick={undoPoint} disabled={points.length === 0 || calibrationMutation.isPending}>
                <Undo2 aria-hidden="true" className="h-4 w-4" />
                Undo
              </Button>
              <Button type="button" variant="secondary" onClick={resetPoints} disabled={points.length === 0 || calibrationMutation.isPending}>
                <RotateCcw aria-hidden="true" className="h-4 w-4" />
                Reset
              </Button>
            </div>
          </div>

          <div className="relative overflow-hidden rounded-md border border-court-line bg-court-panel">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={getArtifactUrl(analysisId, selectedFrame.path)}
              alt="Manual calibration frame"
              className={cn(
                "block max-h-[70vh] w-full object-contain",
                nextStep && "cursor-crosshair",
              )}
              onClick={handleImageClick}
              onLoad={handleImageLoad}
            />
            {imageSize ? <CalibrationOverlay points={points} imageSize={imageSize} /> : null}
          </div>
        </div>

        <aside className="space-y-4">
          <section className="rounded-md border border-court-line bg-white p-5 shadow-panel">
            <h2 className="text-lg font-semibold text-court-ink">Corner order</h2>
            <ol className="mt-4 space-y-3">
              {CORNER_STEPS.map((step, index) => {
                const point = points.find((item) => item.id === step.id);
                const active = nextStep?.id === step.id;
                return (
                  <li
                    key={step.id}
                    className={cn(
                      "rounded-md border p-3 text-sm",
                      point
                        ? "border-green-200 bg-green-50"
                        : active
                          ? "border-court-green bg-court-panel"
                          : "border-court-line bg-white",
                    )}
                  >
                    <div className="flex items-start gap-3">
                      <span className="grid h-7 w-7 shrink-0 place-items-center rounded-md bg-court-green text-xs font-semibold text-white">
                        {index + 1}
                      </span>
                      <div>
                        <p className="font-semibold text-court-ink">{step.label}</p>
                        <p className="mt-1 text-court-muted">{step.hint}</p>
                      </div>
                    </div>
                  </li>
                );
              })}
            </ol>
          </section>

          <section className="rounded-md border border-court-line bg-white p-5 shadow-panel">
            <h2 className="text-lg font-semibold text-court-ink">Review and submit</h2>
            <p className="mt-2 text-sm leading-6 text-court-muted">
              Court4 will submit the points to the backend in near-left, near-right,
              far-right, far-left order.
            </p>
            {!validation.valid ? (
              <p className="mt-4 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm font-medium text-court-ink">
                {validation.message}
              </p>
            ) : null}
            {calibrationMutation.isError ? (
              <CalibrationError error={calibrationMutation.error} />
            ) : null}
            <Button
              className="mt-4 w-full"
              type="button"
              disabled={!validation.valid || calibrationMutation.isPending}
              onClick={submitManualCalibration}
            >
              {calibrationMutation.isPending ? "Saving calibration" : "Save Manual Calibration"}
            </Button>
          </section>
        </aside>
      </section>

      {calibrationMutation.isSuccess ? (
        <section className="rounded-md border border-green-200 bg-green-50 p-5 shadow-panel">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="flex gap-3">
              <CheckCircle2 aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-court-green" />
              <div>
                <h2 className="text-lg font-semibold text-court-ink">Manual calibration saved</h2>
                <p className="mt-1 text-sm leading-6 text-court-muted">
                  Review the generated court artifacts, then continue to player tracking.
                </p>
              </div>
            </div>
            <ButtonLink href={`/matches/${analysisId}#player-tracking`}>
              Continue to Find Players
            </ButtonLink>
          </div>
          <div className="mt-5 grid gap-4 md:grid-cols-2">
            {verification ? (
              <CalibrationArtifact analysisId={analysisId} artifact={verification} label="Verification artifact" />
            ) : null}
            {topDown ? (
              <CalibrationArtifact analysisId={analysisId} artifact={topDown} label="Top-down court artifact" />
            ) : null}
          </div>
        </section>
      ) : null}
    </div>
  );
}

function CalibrationOverlay({
  points,
  imageSize,
}: {
  points: CalibrationPoint[];
  imageSize: ImageSize;
}) {
  const polygonPoints = points.map((point) => `${point.x},${point.y}`).join(" ");

  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0">
      <svg
        className="absolute inset-0 h-full w-full"
        preserveAspectRatio="none"
        viewBox={`0 0 ${imageSize.width} ${imageSize.height}`}
      >
        {points.length >= 2 ? (
          <polyline
            points={polygonPoints}
            fill={points.length === 4 ? "rgba(156, 191, 51, 0.20)" : "none"}
            stroke="#9cbf33"
            strokeWidth="3"
            vectorEffect="non-scaling-stroke"
          />
        ) : null}
      </svg>
      {points.map((point, index) => (
        <span
          key={point.id}
          className="pointer-events-none absolute grid h-8 w-8 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full border-2 border-white bg-court-green text-sm font-semibold text-white shadow-panel"
          style={{
            left: `${toPercent(point.x, imageSize.width)}%`,
            top: `${toPercent(point.y, imageSize.height)}%`,
          }}
        >
          {index + 1}
        </span>
      ))}
    </div>
  );
}

function CalibrationArtifact({
  analysisId,
  artifact,
  label,
}: {
  analysisId: string;
  artifact: AnalysisArtifact;
  label: string;
}) {
  return (
    <figure className="overflow-hidden rounded-md border border-court-line bg-white">
      <div className="aspect-video bg-court-panel">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={getArtifactUrl(analysisId, artifact.path)}
          alt={label}
          className="h-full w-full object-contain"
        />
      </div>
      <figcaption className="border-t border-court-line px-4 py-3 text-sm font-semibold text-court-ink">
        {label}
      </figcaption>
    </figure>
  );
}

function CalibrationError({ error }: { error: unknown }) {
  const normalized = normalizeApiError(error);
  return (
    <div className="mt-4 rounded-md border border-red-200 bg-red-50 p-4 text-sm text-court-red">
      <p className="font-semibold">Manual calibration could not be saved</p>
      <p className="mt-1">{normalized.message}</p>
    </div>
  );
}

function selectFrame(frames: SampledFrame[], selectedFramePath: string | null): SampledFrame | null {
  if (frames.length === 0) {
    return null;
  }
  return frames.find((frame) => frame.path === selectedFramePath) ?? frames[0] ?? null;
}

function validateCalibration(
  points: CalibrationPoint[],
  imageSize: ImageSize | null,
): { valid: boolean; message: string | null } {
  if (!imageSize) {
    return { valid: false, message: "Wait for the frame image to finish loading." };
  }
  if (points.length < 4) {
    const next = CORNER_STEPS[points.length];
    return {
      valid: false,
      message: next ? `Mark ${next.label.toLowerCase()} next.` : "Mark all four corners.",
    };
  }
  if (points.some((point) => !isInsideImage(point, imageSize))) {
    return { valid: false, message: "All points must be inside the frame." };
  }
  if (!pointsAreDistinct(points)) {
    return { valid: false, message: "Each corner must be a distinct point." };
  }

  const ordered = backendOrder(points);
  const area = polygonArea(ordered);
  if (area < MIN_POLYGON_AREA_PIXELS) {
    return { valid: false, message: "The selected court polygon is too small." };
  }
  if (isSelfIntersecting(ordered) || !isConvex(ordered)) {
    return {
      valid: false,
      message: "The selected corners must form one non-crossing court polygon.",
    };
  }
  return { valid: true, message: null };
}

function backendOrder(points: CalibrationPoint[]): CalibrationPoint[] {
  const byId = Object.fromEntries(points.map((point) => [point.id, point])) as Record<
    CornerId,
    CalibrationPoint
  >;
  return [byId.near_left, byId.near_right, byId.far_right, byId.far_left];
}

function pointsAreDistinct(points: CalibrationPoint[]): boolean {
  for (let first = 0; first < points.length; first += 1) {
    for (let second = first + 1; second < points.length; second += 1) {
      if (distance(points[first], points[second]) < DISTINCT_POINT_DISTANCE_PIXELS) {
        return false;
      }
    }
  }
  return true;
}

function isInsideImage(point: { x: number; y: number }, imageSize: ImageSize): boolean {
  return point.x >= 0 && point.x < imageSize.width && point.y >= 0 && point.y < imageSize.height;
}

function polygonArea(points: CalibrationPoint[]): number {
  let area = 0;
  for (let index = 0; index < points.length; index += 1) {
    const current = points[index];
    const next = points[(index + 1) % points.length];
    area += current.x * next.y - next.x * current.y;
  }
  return Math.abs(area) / 2;
}

function isSelfIntersecting(points: CalibrationPoint[]): boolean {
  return (
    segmentsIntersect(points[0], points[1], points[2], points[3]) ||
    segmentsIntersect(points[1], points[2], points[3], points[0])
  );
}

function isConvex(points: CalibrationPoint[]): boolean {
  const signs = [];
  for (let index = 0; index < points.length; index += 1) {
    const previous = points[index];
    const current = points[(index + 1) % points.length];
    const next = points[(index + 2) % points.length];
    signs.push(cross(previous, current, next));
  }
  return signs.every((value) => value > 0) || signs.every((value) => value < 0);
}

function segmentsIntersect(
  firstStart: CalibrationPoint,
  firstEnd: CalibrationPoint,
  secondStart: CalibrationPoint,
  secondEnd: CalibrationPoint,
): boolean {
  const first = orientation(firstStart, firstEnd, secondStart);
  const second = orientation(firstStart, firstEnd, secondEnd);
  const third = orientation(secondStart, secondEnd, firstStart);
  const fourth = orientation(secondStart, secondEnd, firstEnd);
  return first !== second && third !== fourth;
}

function orientation(a: CalibrationPoint, b: CalibrationPoint, c: CalibrationPoint): number {
  const value = cross(a, b, c);
  if (Math.abs(value) < Number.EPSILON) {
    return 0;
  }
  return value > 0 ? 1 : -1;
}

function cross(a: CalibrationPoint, b: CalibrationPoint, c: CalibrationPoint): number {
  return (b.x - a.x) * (c.y - b.y) - (b.y - a.y) * (c.x - b.x);
}

function distance(first: CalibrationPoint, second: CalibrationPoint): number {
  return Math.hypot(second.x - first.x, second.y - first.y);
}

function toRequestPoint(point: CalibrationPoint): { x: number; y: number } {
  return { x: point.x, y: point.y };
}

function toPercent(value: number, total: number): number {
  return (value / total) * 100;
}

function findArtifact(artifacts: AnalysisArtifact[], filename: string): AnalysisArtifact | undefined {
  return artifacts.find((artifact) => artifact.path.endsWith(`/${filename}`));
}
