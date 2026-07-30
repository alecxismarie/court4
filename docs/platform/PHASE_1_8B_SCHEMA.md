# Phase 1.8B Schema

Revision `0001_phase_1_8b` is the clean production lineage. It does not depend on
the Phase 1.8B0 spike revision or its `spike_*` tables.

| Table | Authority |
| --- | --- |
| `users` | Stable identity-ready owner and account state |
| `uploaded_videos` | Source byte metadata, checksum, upload state, owner |
| `analyses` | Public opaque ID, owner, upload, state/stage, projection, promoted run |
| `analysis_runs` | Attempts, active/terminal state, provenance, lease, errors |
| `analysis_state_events` | Append-only analysis/run transition evidence |
| `idempotency_records` | Owner/scope/key reservation and resolved resource |
| `analysis_artifacts` | Provider-neutral key, kind, size, MIME type, checksum, run |
| `player_selections` | Current selection and source candidate/track identity |

## Key invariants

- Analysis-to-video ownership uses a composite foreign key.
- Artifact and player-selection ownership use composite analysis/owner keys.
- Artifact and player-selection run references must belong to the same analysis.
- A partial unique index permits only one queued-or-processing run.
- A partial unique index permits only one current player selection.
- Artifact provider/key is unique per analysis.
- Idempotency is unique per owner, scope, and hashed key.
- Check constraints constrain every state domain and positive row version.
- `promoted_run_id` must reference a run for the same analysis.

## Identifier policy

`analyses.id` remains a safe opaque string up to 64 characters so existing UUID
hex IDs and explicit legacy IDs can be preserved. New internal entities use
UUIDs. Raw tracking IDs remain integers; candidate IDs remain opaque strings;
artifact keys are normalized relative POSIX paths. Absolute paths are never
stored.

## Provenance

Every run freezes the source checksum, pipeline version, schema version, policy
version, configuration fingerprint, software commit identifier, and deployment
build identifier. Every artifact carries a SHA-256 checksum and may carry its
own schema version.

## Transaction boundaries

Upload reservation creates idempotency, uploaded video, analysis, first run, and
initial events in one transaction. Workflow byte generation is outside the
transaction. Job state, terminal run state, promotion, events, and the complete
artifact metadata projection commit together. Database sessions never span CV
processing or file streaming.
