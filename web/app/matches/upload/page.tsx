import { UploadDropzone } from "@/components/upload-dropzone";

export default function UploadMatchPage() {
  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <section className="rounded-md border border-court-line bg-white p-6 shadow-panel">
        <p className="text-sm font-semibold uppercase tracking-wide text-court-green">
          Upload Match
        </p>
        <h1 className="mt-2 text-3xl font-semibold text-court-ink">Start a new analysis</h1>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-court-muted">
          The backend will inspect the video and sample frames. Calibration, player selection,
          and analytics are separate follow-up steps.
        </p>
      </section>
      <UploadDropzone />
    </div>
  );
}
