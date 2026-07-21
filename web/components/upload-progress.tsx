import type { UploadProgress as UploadProgressValue } from "@/lib/api/types";

export function UploadProgress({ progress }: { progress: UploadProgressValue }) {
  const percent = progress.percent ?? 0;
  const label =
    progress.percent === null ? `${progress.loaded} bytes uploaded` : `${percent}% uploaded`;

  return (
    <div className="rounded-md border border-court-line bg-white p-4" aria-live="polite">
      <div className="mb-2 flex items-center justify-between text-sm">
        <span className="font-medium text-court-ink">Uploading video</span>
        <span className="text-court-muted">{label}</span>
      </div>
      <div
        role="progressbar"
        aria-label="Upload progress"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={progress.percent ?? undefined}
        className="h-3 overflow-hidden rounded-md bg-court-panel"
      >
        <div
          className="h-full rounded-md bg-court-blue"
          style={{ width: `${Math.max(5, Math.min(100, percent))}%` }}
        />
      </div>
    </div>
  );
}
