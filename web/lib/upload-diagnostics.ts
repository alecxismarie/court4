import { Court4ApiError } from "@/lib/api/client";

type Event = "preparation_start" | "preparation_end" | "session_bound" |
  "transfer_start" | "transfer_end" | "part_start" | "part_end" | "part_retry" |
  "part_stalled" | "url_renewal_start" | "url_renewal_end";
export type FailureCategory = "success" | "canceled" | "network" | "inactivity" |
  "storage_authorization" | "http" | "missing_receipt" | "other";
type Fields = Partial<Record<"bytes" | "chunks" | "duration_ms" | "part_number" | "attempt" |
  "active_parts" | "max_active_parts" | "part_count" | "retries" | "renewals" |
  "completed_parts" | "existing_parts" | "existing_bytes" | "transferred_bytes" |
  "effective_mbps" | "idle_ms", number>> & {
  outcome?: FailureCategory;
  reason?: "near_expiry" | "expired" | "authorization_rejection" | "recovery_resume";
};
let sequence = 0;

// Browser console only: no telemetry requests, persistence, filenames or identities.
// A run ID links preparation to the eventual server-issued session ID.
export class UploadDiagnostics {
  private readonly runId = `${Date.now()}-${++sequence}`;
  private sessionId?: string;
  private remaining = 2048;

  bind(sessionId: string) {
    this.sessionId = sessionId;
    this.emit("session_bound");
  }

  emit(event: Event, fields: Fields = {}) {
    if (this.remaining-- <= 0) return;
    try {
      console.info("court4_upload", JSON.stringify({
        event, timestamp: new Date().toISOString(), run_id: this.runId,
        upload_session_id: this.sessionId, ...fields,
      }));
    } catch {
      // Diagnostics must never interrupt an upload.
    }
  }
}

export function uploadFailure(error: unknown): FailureCategory {
  if (error instanceof DOMException && error.name === "AbortError") return "canceled";
  if (!(error instanceof Court4ApiError)) return "other";
  if (error.code === "upload_canceled") return "canceled";
  if (error.code === "upload_part_stalled") return "inactivity";
  if (error.code === "upload_provider_unreachable") return "network";
  if (error.code === "missing_upload_etag") return "missing_receipt";
  if (error.code === "upload_part_failed" && [401, 403].includes(error.status ?? 0)) return "storage_authorization";
  return error.status ? "http" : "other";
}
