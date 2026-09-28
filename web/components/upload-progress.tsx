import type { UploadProgress as UploadProgressValue } from "@/lib/api/types";

export function UploadProgress({ progress }: { progress: UploadProgressValue }) {
  const percent = progress.percent ?? 0;
  const isVerifying = progress.phase === "verifying";
  const isPreparing = progress.phase === "preparing";
  const label =
    isPreparing ? "Checking your file"
      : isVerifying
      ? "Upload complete"
      : progress.percent === null
        ? `${progress.loaded} bytes uploaded`
        : `${percent}% uploaded`;

  return (
    <div className="rounded-md border border-court-line bg-white p-4" aria-live="polite">
      <div className="mb-2 flex items-center justify-between text-sm">
        <span className="font-medium text-court-ink">
          {isPreparing ? "Preparing video" : isVerifying ? "Verifying and finalizing video" : "Uploading video"}
        </span>
        <span className="text-court-muted">{label}</span>
      </div>
      <div
        role="progressbar"
        aria-label={isPreparing ? "File preparation" : "Upload progress"}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={isPreparing ? undefined : progress.percent ?? undefined}
        className="h-3 overflow-hidden rounded-md bg-court-panel"
      >
        <div
          className="h-full rounded-md bg-court-lime"
          style={{ width: `${Math.max(0, Math.min(100, percent))}%` }}
        />
      </div>
      <p className="mt-2 text-sm text-court-muted">
        {isPreparing ? "Checking the file on your device before uploading. No video bytes are being sent yet."
          : isVerifying ? "Your video has arrived. Court4 is checking it before court setup; your analysis is not complete yet."
            : "This shows video transfer only. Court setup, player selection, and analysis come next."}
      </p>
    </div>
  );
}
