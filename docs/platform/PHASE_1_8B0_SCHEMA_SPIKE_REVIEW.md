# Phase 1.8B0 Schema Spike Review

## Decision

The PostgreSQL model is ready to guide full Phase 1.8B. The experimental migration
must be discarded and regenerated from the complete, unprefixed schema. No Phase
1.8A ADR is reversed: PostgreSQL authority, single ownership, separate logical
analyses and attempts, provenance-preserving reprocessing, scoped idempotency, and
queue-ready leases were all confirmed.

The design recommendation is unchanged. The formal concurrency-spike closeout
verdict is **READY WITH TEST CHANGES**: F and G already forced both original reads
with a barrier, but closeout added deterministic winner ordering, rejected-actor
backend-PID evidence, ten repetitions, and exact committed-event/no-partial-write
assertions.

## Review checkpoint

### 1. Is separating Analysis from AnalysisRun still correct?

Yes. Twenty-way run-start and stale-replacement contention produced one active
attempt while preserving the logical Analysis and the old attempt. Folding the
attempt into Analysis would either overwrite evidence or complicate reprocessing.

### 2. What should each entity own?

Analysis owns owner, source upload, logical request/options, presentation metadata,
aggregate lifecycle, deletion/supersession, and eventually the promoted current
result. AnalysisRun owns attempt state, immutable provenance, claim/lease data,
failure details, previous-attempt relationship, artifacts, and attempt timestamps.

### 3. Where should idempotency be scoped?

At minimum by authenticated owner, command scope, and SHA-256 key hash. The
fingerprint is compared after the unique row is found. Resource type and ID are
stored with the result. The same key across owners must remain independent.

### 4. Is one-active-run enforcement reliable?

Yes. A PostgreSQL partial unique index on `analysis_id` where state is `queued` or
`processing` allowed exactly one winner in 10 high-contention iterations: five
initial-start and five replacement-start runs, each with 20 connections.

### 5. Are partial unique indexes sufficient?

They are sufficient as the final active-run invariant, but not the whole command
protocol. The service must translate the named constraint, roll back the losing
transaction, resolve the winner, and maintain an owner-scoped idempotency result.
State/event coherence still requires transactional code and compare-and-swap.

### 6. Should state events belong to Analysis, AnalysisRun, or both?

Both subjects should use one append-only event table. A nullable run FK plus an
enforced subject discriminator worked. Full Phase 1.8B should add request/actor
identity and reason fields from Phase 1.8A. Events explain current state and do not
replace it.

### 7. Is optimistic locking required on all entities?

Use it on mutable stateful entities: uploads, analyses, runs, artifacts undergoing
status changes, and deletion records. Immutable/read-mostly evidence and
append-only events do not need row versions. Idempotency relies primarily on its
unique key and status protocol.

### 8. Are the transaction boundaries practical?

Yes. Idempotency claim, ownership check, resource/state mutation, event append, and
result identity fit in one short transaction. External upload and video processing
must remain outside it and report completion in a new compare-and-swap transaction.

### 9. Can the model support future queues and workers?

Yes. Queued/processing states, global attempt identity, claimant-ready provenance,
lease expiry, heartbeat, stale state, and a partial active-run constraint do not
assume an in-process executor.

### 10. Can workers use leases and `FOR UPDATE SKIP LOCKED` later?

Yes. A worker can select queued runs by creation/attempt order with
`FOR UPDATE SKIP LOCKED`, change one to processing, set claimant/lease/heartbeat,
increment its row version, and append an event. No ownership or relationship change
is required. The full schema should add `claimed_by` and a queued-scan index.

### 11. Which Phase 1.8A assumptions were confirmed?

- PostgreSQL must be the source of truth.
- Upload owner and Analysis owner must match at the database boundary.
- Analysis and AnalysisRun are separate.
- A partial unique active-run index is the final concurrency authority.
- Owner/scope/key idempotency plus a request fingerprint is deterministic.
- State update and event append belong in one transaction.
- Row-version compare-and-swap prevents silent last-write-wins.
- Frozen run provenance and previous-run links preserve reprocessing history.
- Leases and heartbeats are justified before a queue is introduced.
- The filesystem runtime can remain untouched during an incremental transition.

### 12. Which assumptions changed or were rejected?

- A contiguous per-Analysis `run_number` was not used. Allocating it safely requires
  an aggregate row lock or a retryable unique conflict and adds a hotspot. The spike
  used a database identity-backed global `attempt_number`. If a per-analysis display
  number is required, allocate it while deliberately locking Analysis.
- A mandatory per-Analysis event `sequence_number` was not needed for write safety.
  UUID, subject row version, and timestamp are enough for the spike. If strict event
  ordering is a product requirement, allocate the number under the same aggregate
  lock; do not use `max(sequence)+1`.
- `analyses.current_run_id` is not the active-run authority and was omitted. Add it
  only with the artifact-promotion transaction and a same-analysis composite FK.
- Pessimistically locking Analysis before every run insert is not required for the
  one-active invariant. The partial unique index is authoritative; locks remain
  useful for current-result promotion and cross-field aggregate decisions.
- The spike used an explicit `stale` terminal attempt. Phase 1.8A described
  `failed` plus `stale_lease`. Full Phase 1.8B must choose one representation and
  keep the reason auditable; do not support both ambiguously.

### 13. Which provisional tables or fields should be removed?

Remove the `spike_` tables wholesale rather than evolving them in production.
Replace the temporary identity label, reduced states, generic event metadata, and
global experimental naming with the complete Phase 1.8B schema. Retain the
validated concepts and tests, not this migration lineage.

### 14. Did correctness remain intact with 2–20 actors?

Yes. A, B, C, and H used 20 actors; independent owner workflows used 10. Every
high-contention case ran five times. F and G used two actors because each invariant
is a two-writer race and ran ten times each. Each actor had its own Session,
transaction, connection, and PostgreSQL backend PID.

### 15. Were there deadlocks, long waits, or pool starvation?

No. There were no deadlocks, serialization failures, lock/statement timeouts, pool
exhaustion, idle-in-transaction timeouts, or unexpected aborts. Maximum measured
iteration was 669.36 ms. The pool was sized 25 plus 5 overflow for a 20-actor
ceiling.

The prior timeout report was not based on PostgreSQL defaults. A SQLAlchemy
connection event explicitly set `lock_timeout = 5s`, `statement_timeout = 30s`,
and `idle_in_transaction_session_timeout = 30s` on every spike connection. The
closeout uses the preferred test-only values of 5, 10, and 15 seconds,
respectively, and diagnostics assert all three settings. No broad retries were
introduced to mask timeout failures. The complete closeout suite triggered none of
the limits, and its longest contended iteration was below one second.

### 16. Are conflict outcomes deterministic enough for future APIs?

Yes. Outcomes map cleanly to original-resource replay, idempotency-key reuse,
existing-active-run resolution, invalid transition, stale resource, ownership
mismatch, and not found. Full API work should assign stable error codes and HTTP
statuses rather than exposing SQL or constraint details.

For F and G specifically, the original controlled hook ran after the row read and a
two-party `threading.Barrier` forced both actors to observe the same original state
and version. G's winning terminal state could still be selected by scheduling.
Closeout records `(pg_backend_pid, state, row_version)` for both actors, uses the
barrier to prove both observations, and then uses a `threading.Event` to hold actor
1 until actor 0 commits. Ten repetitions now prove an exact legal winner, exact
events, no rejected event, and no partial write for both races.

### 17. Should any operation use bounded database retries?

Not based on this evidence. Zero deadlocks, serialization failures, and timeouts
occurred under required contention. Named uniqueness conflicts are domain
arbitration, not retry candidates. If production later observes SQLSTATE `40001` or
`40P01`, add a small bounded retry only around proven-idempotent transaction
functions, with metrics and jittered backoff.

### 18. Should the provisional migration be retained?

Discard and regenerate. The revision is intentionally prefixed, reduced, and
isolated. Its value is executable evidence. The full migration should start from
the finalized production metadata and be tested through the same empty
upgrade/downgrade/re-upgrade cycle.

The [tracked kickoff checklist](IMPLEMENTATION_ROADMAP.md#phase-18b-kickoff-spike-cleanup-and-quarantine)
requires clean production migrations; ported constraints, transaction patterns,
and regression tests; removal or explicit quarantine of provisional migration,
models, and services; no runtime imports from `spike/`; no apparently active dual
persistence path; and CI verification of every spike invariant against production
persistence.

### 19. Is the schema ready to found full Phase 1.8B?

Yes, as a design foundation—not as a migration to ship. Full Phase 1.8B should
implement the complete users/uploads/analyses/runs/events/idempotency model,
production error mapping, artifact promotion, and current-run integrity using these
validated patterns.

## Migration and deployment recommendation

The spike migration reset cleanly and metadata drift is zero. Discard it before
production schema work. Keep the Compose profile, transaction helpers, contention
tests, and documented constraint names as reference.

Do not expose the existing app publicly yet. It has no production identity or
owner authorization boundary, and its filesystem repository is intentionally still
the runtime source of truth. The recommended order is:

1. complete Phase 1.8B production persistence and ownership-aware repositories;
2. implement the authentication and authorization direction from Phase 1.8A;
3. add production storage, consent, secrets, backup, observability, and deployment
   controls;
4. run deployment acceptance and recovery exercises;
5. then permit public traffic.

Authentication should precede public deployment, but it should follow or be
integrated with the real user/ownership schema rather than being bolted onto the
current filesystem records.
