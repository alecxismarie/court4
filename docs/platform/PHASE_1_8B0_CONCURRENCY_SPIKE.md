# Phase 1.8B0 PostgreSQL Concurrency Spike

## Purpose and isolation

This spike tests the Phase 1.8A persistence assumptions against PostgreSQL 16. It
does not replace the current filesystem repository, change an API route, introduce
authentication, or become a production migration. Nothing under `app/` imports the
`spike` package.

The implementation is opt-in:

- `docker compose --profile spike up -d postgres-spike` starts PostgreSQL on
  `127.0.0.1:55432`;
- the `spike` dependency extra installs SQLAlchemy 2, Alembic, and psycopg 3;
- `COURT4_SPIKE_DATABASE_URL` selects the test database;
- every spike table is prefixed `spike_`;
- the current API and filesystem-backed workflow remain unchanged.

## Provisional schema

| Table | Responsibility | Primary protection |
|---|---|---|
| `spike_users` | Temporary explicit development/test owner | Unique identity label |
| `spike_uploaded_videos` | Owner-scoped upload metadata | Owner FK and `(id, owner_user_id)` uniqueness |
| `spike_analyses` | Logical user analysis across attempts | Composite video/owner FK and row version |
| `spike_analysis_runs` | One processing attempt and its frozen provenance | Partial unique active-run index and row version |
| `spike_analysis_state_events` | Append-only explanation of committed state | Same transaction as the state update |
| `spike_idempotency_records` | Owner/scope/key command result | Unique `(owner_user_id, scope, key_hash)` |

The composite foreign key from an analysis to `(uploaded_video_id,
owner_user_id)` makes a cross-owner analysis invalid even if service validation is
bypassed. A direct invalid insert test confirms PostgreSQL rejects it.

`Analysis` owns the logical request, owner, source video, and aggregate lifecycle.
`AnalysisRun` owns an individual attempt, attempt lifecycle, lease/heartbeat, link
to the preceding attempt, and frozen minimum provenance. A global identity-backed
`attempt_number` was used in the spike instead of allocating a contiguous number
inside each analysis.

## State model

The reduced spike model intentionally covers only the transitions needed to test
write safety.

- Analysis: `created`, `processing`, `completed`, `failed`, `cancelled`.
- Run: `queued`, `processing`, `completed`, `failed`, `cancelled`, `stale`.
- Run transitions: `queued -> processing|cancelled` and
  `processing -> completed|failed|cancelled|stale`.
- `processing -> stale` is legal only when `lease_expires_at` is present and
  expired.

A transition validates the observed state and expected `row_version`, performs an
`UPDATE ... WHERE state = ? AND row_version = ?`, increments the version, and
appends its event in the same transaction. A zero-row update is a deterministic
optimistic-concurrency conflict. Invalid and losing transitions write no event.
Terminal run state is reflected on Analysis in that transaction. An explicit
`stale` run remains auditable and a replacement points to it through
`previous_run_id`.

## Idempotency and transactions

Raw keys are never stored; SHA-256 hashes are scoped by owner and operation.

- Same owner, scope, key, and fingerprint returns the committed resource ID.
- Same scoped key with a different fingerprint raises a deterministic domain
  conflict.
- Different owners may use the same key without sharing a record or resource.
- The idempotency row, resource, initial run, and required events commit together.
- A simulated lost response followed by an identical retry returns the original
  resource without a second resource, run, or event.

Every operation owns a new SQLAlchemy Session and transaction. The contention hook
runs only after `pg_backend_pid()` has forced that transaction to acquire its own
connection. The tests assert all backend PIDs are distinct within every contended
iteration. No Session, transaction, or connection is shared between actors.

### Deterministic F/G closeout

The original F and G tests already used a two-party `threading.Barrier` through a
controlled service hook. In `transition_run`, the hook ran after
`pg_backend_pid()` acquired a connection and after `Session.get()` loaded the run's
state and `row_version`, but before validation or compare-and-swap. They therefore
forced both reads and were not merely two concurrently submitted tasks. The
one-winner outcome was deterministic, although G allowed scheduling to select
which legal terminal transition won. Both tests ran only once and the rejected
actor's PID was not exposed, so the proof was incomplete.

The closeout tests now use two actors and ten fresh repetitions each. An observation
hook records each actor's backend PID, state, and row version after the row read. A
two-party `threading.Barrier` proves both observations are present. A
`threading.Event` then holds actor 1 while actor 0 performs and commits its
transition; actor 0 sets the event only after `transition_run` returns from its
transaction. Actor 1 then evaluates its already-read invalid transition in F or
attempts its stale compare-and-swap in G. The tests assert two distinct
`pg_backend_pid()` values, the exact winning run and Analysis events, absence of a
rejected-actor event, final state and versions, and absence of partial terminal
writes. The designated winner and all persisted results are independent of thread
scheduling.

Active-run creation deliberately does not depend on an application-level
check-then-insert. PostgreSQL's partial unique index on `analysis_id` for
`queued|processing` chooses the sole winner. Losing operations roll back their
attempt and either resolve the committed active run or return a deterministic
domain error. No broad retry loop is used.

## PostgreSQL configuration

- Image: `postgres:16-alpine`; observed server: PostgreSQL 16.14.
- Isolation: `READ COMMITTED`.
- SQLAlchemy pool: 25 persistent connections plus 5 overflow, 10-second pool
  timeout, pre-ping enabled.
- Test-only per-connection limits: 5-second `lock_timeout`, 10-second
  `statement_timeout`, and 15-second `idle_in_transaction_session_timeout`.
  `create_spike_engine` applies all three with a SQLAlchemy `connect` event to
  every new DBAPI connection; pooled connections retain those session settings.
- Maximum test concurrency: 20 actors, within the 30-connection pool ceiling.

The earlier "zero timeouts" result did use explicit limits rather than PostgreSQL
defaults: 5-second lock, 30-second statement, and 30-second idle-in-transaction
timeouts. It did not test the preferred 10/5/15-second closeout values. The
closeout changed statement and idle-in-transaction limits to 10 and 15 seconds,
respectively, retained the 5-second lock limit, and added a diagnostic assertion
for all three values. No retry behavior was added.

## Harness and results

Final measured run: 19 spike/bootstrap tests passed in 17.43 seconds. Durations are
wall-clock time for the complete contended iteration.

| Scenario | Actors | Repetitions | Median | Maximum | Result |
|---|---:|---:|---:|---:|---|
| A. Same key and payload creates one processing analysis | 20 | 5 | 230.89 ms | 348.40 ms | One Analysis, one active run, one ID, exact events |
| B. Same key with distinct fingerprints | 20 | 5 | 215.23 ms | 225.26 ms | One winner; 19 deterministic conflicts per iteration |
| C. Competing starts for one Analysis | 20 | 5 | 477.16 ms | 525.11 ms | One active run; all callers resolve it |
| D/J. Independent owner workflows with the same upload key | 10 | 5 | 217.78 ms | 295.64 ms | Ten uploads and analyses; ownership and IDs remain isolated |
| E. Retry after committed/lost response | sequential retry | 1 | not material | not material | Original resource returned; no extra side effect |
| F. Valid versus invalid transition | 2 | 10 | 28.89 ms | 32.80 ms | Designated legal actor commits; invalid actor and its writes are rejected |
| G. Same-version optimistic conflict | 2 | 10 | 31.41 ms | 34.47 ms | Designated winner commits; stale compare-and-swap and its writes are rejected |
| H. Expired run and replacement contention | 20 | 5 | 624.40 ms | 669.36 ms | Old run becomes stale; one linked replacement |
| I. Bootstrap identity fail-closed variants | parameterized | 9 cases | not material | not material | All unsafe/default configurations rejected |

The required repeated collision cases used clean, separately identified resources
on every iteration. The test fixture truncates the spike tables between tests.

Observed contention outcomes:

- zero PostgreSQL deadlocks;
- zero serialization failures;
- zero lock-wait timeouts;
- zero statement timeouts;
- zero pool exhaustion events;
- zero unexpected transaction aborts;
- zero infrastructure retries;
- 380 expected, caught uniqueness violations selected winners across A, B, C, and
  H;
- one expected, caught composite-ownership FK violation in the direct database
  boundary test.

All losing outcomes were deterministic. Five-iteration scenarios produced no
flake. The run-start case was the slowest because 19 transactions serialize briefly
behind the same unique index and then persist their distinct idempotency
resolutions; its maximum remained below one second in the final run.

The closeout run triggered no lock, statement, or idle-in-transaction timeout.
No test approached the configured bounds: the longest complete contended iteration
was 669.36 ms, below the shortest 5-second database timeout. There were also zero
deadlocks, unexpected database aborts, or flaky repetitions.

## Fail-closed bootstrap identity

The temporary owner is created or resolved only when all of these are explicit:

- environment is exactly `development` or `test`;
- enablement is one of the accepted true values;
- the caller supplies a valid UUID;
- the caller supplies a non-empty identity label.

Production, staging, preview, default/missing configuration, false enablement,
malformed UUID, and empty label all raise before a Session is opened. A PostgreSQL
test confirms a production configuration leaves `spike_users` empty. This mechanism
is temporary and is not an authentication substitute.

## Migration and reset

Revision `0001_phase_1_8b0` upgraded an empty database, downgraded to the empty
schema, and re-upgraded successfully. `alembic check` reported no metadata drift.
PostgreSQL transactional DDL protected each migration direction.

Normal reset:

```powershell
$env:COURT4_SPIKE_DATABASE_URL = "postgresql+psycopg://court4_spike:court4_spike_local_only@127.0.0.1:55432/court4_spike"
alembic -c alembic.ini downgrade base
alembic -c alembic.ini upgrade head
```

The migration is disposable. Before full Phase 1.8B, discard it and generate the
production migration from the finalized unprefixed schema. Do not splice this
experimental revision into a production migration history.

The tracked [Phase 1.8B kickoff checklist](IMPLEMENTATION_ROADMAP.md#phase-18b-kickoff-spike-cleanup-and-quarantine)
also requires the production implementation to port these constraints,
transaction patterns, and concurrency regression tests; remove or explicitly
quarantine the provisional migration, models, and services; prevent all production
runtime imports from `spike/`; avoid an apparently active dual persistence path;
and make CI prove the invariants against production persistence rather than the
spike package.

## Rejected alternatives

- Process locks and in-memory idempotency cannot coordinate multiple API/worker
  processes.
- Check-then-insert without a unique constraint has two winners under contention.
- Holding a database transaction during video processing creates unacceptable lock
  and pool pressure.
- Reusing a terminal run destroys attempt provenance.
- A silent fallback owner would turn configuration errors into cross-user data
  exposure.
- Broad deadlock or integrity retries would hide contention behavior and could
  repeat non-idempotent work.

## Recommendation

Proceed to full Phase 1.8B using the validated transaction patterns and database
constraints, then implement real authentication/authorization before any
publicly reachable deployment. The current filesystem runtime is suitable only for
local development or a tightly controlled private demo; the spike is evidence, not
a production persistence integration. The design recommendation did not change;
the formal closeout verdict is **READY WITH TEST CHANGES** because deterministic
winner control, rejected-actor PID evidence, ten repetitions, and exact event
assertions were added.
