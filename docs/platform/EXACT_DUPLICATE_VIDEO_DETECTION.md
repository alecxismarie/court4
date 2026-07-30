# Exact Duplicate Video Detection

Court4 detects byte-identical video uploads before creating a second analysis.
The check is scoped to the current owner and uses the SHA-256 checksum recorded
for uploaded videos.

## Upload flow

1. Court4 calculates SHA-256 while streaming the upload to staging storage.
2. It checks idempotency first. A retry with the same `Idempotency-Key` returns
   the original response.
3. For a new upload intent, Court4 acquires a transaction-scoped PostgreSQL
   advisory lock derived from the owner ID and checksum.
4. It searches `uploaded_videos` for the same owner and checksum.
5. If a match exists, Court4 returns the existing analysis instead of creating a
   second uploaded-video or analysis record.

The supporting `(owner_user_id, source_checksum)` index is intentionally
non-unique. Choosing **Analyze Again** is an explicit request to preserve another
analysis of the same bytes.

## API contract

The first upload, or an explicit Analyze Again request, returns HTTP `201` with
the normal queued analysis response.

A byte-identical upload from the same owner returns HTTP `200`:

```json
{
  "status": "duplicate",
  "duplicate_type": "exact",
  "existing_analysis_id": "analysis-id",
  "uploaded_at": "2026-07-30T10:00:00Z",
  "actions": {
    "open_existing": true,
    "reanalyze": true
  }
}
```

The client offers three choices:

- **Open Existing Analysis** navigates to the existing analysis.
- **Analyze Again** sends `reanalyze=true` with a new idempotency key and creates
  a new upload and analysis. The earlier analysis and its provenance remain
  unchanged.
- **Cancel** dismisses the duplicate prompt without creating anything.

This phase deliberately retains the current physical-file lifecycle. It does not
introduce shared storage objects or reference counting.

## Idempotency and duplicate detection

These controls solve different problems:

- **Idempotency** identifies a retry of the same upload intent. Reusing the same
  `Idempotency-Key` returns that intent's original result, including an original
  queued analysis or duplicate response.
- **Duplicate detection** identifies a new upload intent whose bytes match a
  prior upload from the same owner.

The web client creates one key when a file is selected, reuses it for network
retries, and creates a new key only for a new file selection or Analyze Again.

## Concurrency

The advisory lock serializes identical uploads for one owner before the database
lookup and insert. Consequently, simultaneous requests with different
idempotency keys create at most one initial analysis; the remaining requests
receive the typed duplicate response.

The lock and lookup include the owner ID. Identical bytes uploaded by different
owners do not block one another and are treated as independent uploads.

## Privacy boundary

Duplicate detection never performs a global checksum lookup. It does not reveal
whether another owner uploaded matching bytes, and it never exposes another
owner's analysis ID, upload time, filename, or any other metadata.

## Detection limit

This mechanism recognizes only exact byte-for-byte matches. Re-encoding,
trimming, changing metadata, or otherwise modifying a video produces a different
checksum and is treated as a new upload. Perceptual fingerprinting may be
considered as a future, separately designed privacy-conscious capability; it is
not part of this implementation.
