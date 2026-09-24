"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { abortDirectUpload, completeDirectUpload, createAnalysis, discoverUploads, recoverUpload, waitForUploadResult } from "@/lib/api/analyses";
import { normalizeApiError } from "@/lib/api/client";
import type { UploadAnalysisResponse, UploadProgress as Progress, UploadRecovery } from "@/lib/api/types";
import { UploadDropzone } from "@/components/upload-dropzone";
import { UploadProgress } from "@/components/upload-progress";
import { Button } from "@/components/ui/button";
import { rememberAnalysisId } from "@/lib/recent-analyses";
import { useAuth } from "@/lib/auth-context";

export function UploadRecoveryWorkspace() {
  const { user } = useAuth();
  return <OwnerUploadWorkspace key={user?.id} />;
}

function OwnerUploadWorkspace() {
  const [uploads, setUploads] = useState<UploadRecovery[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const reload = useCallback(async () => {
    setError(null);
    try { setUploads(await discoverUploads()); }
    catch { setError("Your previous upload could not be checked. Reconnect and try again."); }
  }, []);
  useEffect(() => {
    let active = true;
    discoverUploads().then((rows) => { if (active) setUploads(rows); })
      .catch(() => { if (active) setError("Your previous upload could not be checked. Reconnect and try again."); });
    return () => { active = false; };
  }, []);
  if (error) return <section role="alert"><p>{error}</p><Button onClick={() => void reload()}>Check for upload</Button></section>;
  if (uploads === null) return <p role="status">Checking for an interrupted upload…</p>;
  if (uploads.length) return <RecoveredUpload key={uploads[0].upload_session_id} initial={uploads[0]} onCanceled={reload} />;
  return <UploadDropzone onInterrupted={() => void reload()} />;
}

function confirmedProgress(upload: UploadRecovery): Progress {
  const finalizing = ["completing", "verifying", "analyzing", "completed"].includes(upload.status);
  const loaded = finalizing ? upload.byte_size : upload.completed_parts.reduce((sum, part) => sum + part.size_bytes, 0);
  return { loaded, total: upload.byte_size, percent: Math.floor(loaded / upload.byte_size * 100), phase: finalizing ? "verifying" : "uploading" };
}

function RecoveredUpload({ initial, onCanceled }: { initial: UploadRecovery; onCanceled: () => Promise<void> }) {
  const router = useRouter();
  const [upload, setUpload] = useState(initial);
  const [file, setFile] = useState<File | null>(null);
  const [progress, setProgress] = useState(() => confirmedProgress(initial));
  const [busy, setBusy] = useState(false);
  const [canceling, setCanceling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  const finalizing = ["completing", "verifying", "analyzing", "completed"].includes(upload.status);
  const allParts = upload.completed_parts.length === upload.part_count;
  const expired = upload.status === "expired";

  function finish(result: UploadAnalysisResponse) {
    const id = "existing_analysis_id" in result ? result.existing_analysis_id : "analysis_id" in result ? result.analysis_id : null;
    if (id) { rememberAnalysisId(id); router.push(`/matches/${id}`); }
  }

  async function resume() {
    setBusy(true); setError(null);
    const attempt = new AbortController(); controller.current = attempt;
    try {
      const current = await recoverUpload(upload.upload_session_id);
      setUpload(current); setProgress(confirmedProgress(current));
      let result: UploadAnalysisResponse;
      if (["completing", "verifying", "analyzing", "completed"].includes(current.status)) {
        result = await waitForUploadResult(current.upload_session_id, { size: current.byte_size }, setProgress, attempt.signal);
      } else if (current.completed_parts.length === current.part_count) {
        result = await completeDirectUpload(current.upload_session_id, current.completed_parts, current.byte_size, setProgress, attempt.signal);
      } else {
        if (!file) throw new Error("Reselect the original video to continue.");
        result = await createAnalysis(file, setProgress, { resumeSessionId: current.upload_session_id, signal: attempt.signal });
      }
      if (!attempt.signal.aborted) finish(result);
    } catch (caught) {
      setError(normalizeApiError(caught).message);
      try { const latest = await recoverUpload(upload.upload_session_id); setUpload(latest); setProgress(confirmedProgress(latest)); } catch { /* Keep the last known progress; never invent zero. */ }
    } finally { setBusy(false); controller.current = null; }
  }

  async function cancel() {
    setCanceling(true); controller.current?.abort();
    try {
      if (await abortDirectUpload(upload.upload_session_id)) await onCanceled();
      else setError("The upload could not be canceled. Sign in or reconnect and check its status before trying again.");
    } finally { setCanceling(false); }
  }

  return <section className="space-y-5 rounded-md border border-court-line bg-white p-6">
    <h1 className="text-2xl font-semibold">{busy ? finalizing || progress.phase === "verifying" ? "Finalizing" : "Uploading" : error ? "Upload interrupted" : "Recoverable upload found"}</h1>
    <p>{upload.filename}</p>
    <p>Your uploaded parts are preserved. {finalizing ? "Check progress to continue finalizing." : allParts ? "All parts have arrived. You can finish without uploading the video again." : "Reselect the original video to resume the remaining parts."}</p>
    <UploadProgress progress={progress} />
    {!finalizing && !allParts && !expired && upload.file_identity ? <label className="block">Original match video
      <input type="file" accept=".mp4,.mov,.avi,.mkv" disabled={busy || canceling} onChange={(event) => setFile(event.target.files?.item(0) ?? null)} />
      <span className="block text-sm">Court4 checks the entire file before resuming. Checking a large video may take a moment.</span>
    </label> : null}
    {!upload.file_identity && !allParts && !finalizing ? <p>This older upload has no file verification record, so its remaining parts cannot be resumed safely. You can explicitly cancel it.</p> : null}
    {expired ? <p>This upload has expired. Cancel it before starting another upload.</p> : null}
    {error ? <p role="alert">{error}</p> : null}
    <div className="flex gap-3">
      <Button onClick={() => void resume()} disabled={busy || canceling || (expired && !finalizing) || (!finalizing && !allParts && (!file || !upload.file_identity))}>
        {finalizing ? "Check progress" : allParts ? "Finish upload" : "Resume upload"}
      </Button>
      <Button variant="secondary" onClick={() => void cancel()} disabled={canceling || finalizing}>Cancel upload</Button>
    </div>
  </section>;
}
