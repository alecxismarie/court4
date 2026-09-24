# Refresh 401 diagnostics

The September 23 long-upload incident showed refresh 401s after an earlier
`auth_refresh_rotated`, without a reuse event in the inspected range. That does
not establish which refresh rejection branch ran. This instrumentation changes
only trusted server logs; public failures remain HTTP 401 with `invalid_session`
and `Session is invalid.`

## Events and bounded reasons

`app.auth.service` emits INFO `auth_refresh_rejected` with `context.reason`:

| Reason | Exact observation | Limits |
| --- | --- | --- |
| `cookie_missing` | Refresh service received `None` for the configured cookie | Does not identify browser policy, configuration, or intermediary cause |
| `token_invalid` | Present value failed existing parsing: empty, over 256 characters, missing separator, invalid UUID, or secret under 32 characters | Does not log or explain the original value |
| `session_not_found` | Initial or locked refresh-session lookup yielded no row | Does not distinguish wrong database, deletion, or unknown ID |
| `token_mismatch` | Existing row's hash did not match, initially or on locked re-read | Does not identify the source of the mismatch |
| `session_expired` | Unrevoked matching session reached its stored expiry | Does not prove live lifetime settings or why a cookie was still sent |
| `session_revoked` | Matching session was already revoked for a non-rotation reason | Does not identify the revocation cause; consult existing events or authorized metadata inspection |
| `account_missing` | Matching, unrevoked, unexpired session but account lookup returned no user | Defensive concurrency path; ordinary account deletion cascades session deletion and normally yields `session_not_found` |
| `account_inactive` | Matching, unrevoked, unexpired session but account was not active | Does not identify why the account was disabled |

The log collector must retain INFO events to observe these reasons. Origin
validation and rate limiting run before the refresh service; their 403/429
responses do not emit this event. Runtime/database errors also remain distinct
from diagnosed refresh 401s.

Parsing failures log immediately before re-raising the existing exception.
Database decisions retain their reason locally and log after the existing
transaction exits, immediately before the existing sanitized rejection. No
queries, writes, commits, or transaction boundaries are added. New events contain
only the bounded reason, without account or session identifiers.

Existing WARNING `auth_refresh_reuse_detected` is preserved without a second
generic rejection event. It identifies a matching token already revoked as
`rotated`, and the existing code attempts to revoke active members of that family.
That event remains inside the transaction, so it proves detection, not necessarily
successful commit if a subsequent database failure occurs. INFO
`auth_refresh_rotated` remains after a successful rotation commit; it does not
prove the browser accepted the replacement cookie. Neither event proves a
multi-tab race. Both retain their existing safe `context.user_id` correlation.

An already expired-and-revoked session logs `session_revoked` on later attempts:
revocation is checked before expiry. Reuse-revoked successor tokens also log
`session_revoked`. Public responses never disclose these distinctions.

## Later deployment and reproduction

This change is not deployed as part of the task. After a separately authorized
deployment, log in normally and start a representative multipart upload. Let the
access-token boundary pass naturally (time is measured from token issuance, not
upload initiation). Observe normal completion and refresh behavior. Do not edit,
copy, replay, or expose cookies/tokens, and do not shorten staging lifetimes.

Search API logs across relevant replicas for:

- `auth_refresh_rejected` and its `context.reason`
- `auth_refresh_rotated`
- `auth_refresh_reuse_detected`
- `auth_login_succeeded`
- `/api/v1/auth/refresh`
- the upload's completion and cancellation request paths
- `api_unexpected_error` for transaction/runtime failures

Use the reproduction interval with several minutes of margin; compare embedded
UTC timestamps with Railway display/ingestion times. Generic rejection events
have no user/request identifier; close timestamps alone are not definitive
correlation in concurrent traffic. Never export raw HARs or auth headers.

For the historical incident, inspect September 23, 2026, 16:45-17:15 Singapore
time (08:45-09:15 UTC). New events cannot retrospectively diagnose old requests.

Use the observed reason to narrow the next read-only investigation: browser
cookie delivery for missing/invalid values; authorized session metadata for
unknown, expired, revoked, or mismatched sessions; account-state evidence for
account rejection; concurrent request timing for reuse. Design a separate fix
only after the cause is established. Focused automated tests exercise expiry in
the isolated test database, without changing staging TTLs.

## Configuration clarification and security

Actual lifetime fields read `PICKLEBALL_AI_AUTH_ACCESS_TOKEN_MINUTES` and
`PICKLEBALL_AI_AUTH_REFRESH_TOKEN_DAYS` (defaults 10 and 30). The supplied names
ending in `TOKEN_TTL_MINUTES` / `TOKEN_TTL_DAYS` are not supported settings.
There are no `AUTH_COOKIE_DOMAIN` / `AUTH_COOKIE_PATH` settings: cookies are
host-only, with path derived from the API base path. Absence of unsupported
variables does not establish whether the actual lifetime variables are set.
Reported live Secure=true and SameSite=none are not changed by this patch.

Never log token/cookie values (even truncated), hashes, headers, signing material,
credentials, email addresses, or user agents. Tests assert serialized auth-event
payloads omit generated test authentication material. Authentication, rotation,
reuse revocation, cookie security, CORS, rate limits, uploads, and media deletion
remain unchanged. No migration is involved.

## Local validation and review (September 24, 2026)

The existing working-tree implementation was retained. The production diff is
limited to `AuthenticationService.refresh`: fixed reason assignments and log
emission, plus catching and re-raising the existing parsing exception. Review
against HEAD found no changed auth decisions, SQL queries, writes, locking,
transaction boundaries, public responses, or cookie behavior. No auth fix,
deployment, Railway change, commit, or push is part of this work.

Validation uses the rebuilt `court4:test-local` Docker image and the guarded
`postgres-test` database. The test runner overrides its allowed origin and
frontend base URL to `http://localhost:3000` for the existing HTTP fixtures;
production and staging settings are untouched.
Current tests, `Dockerfile`, and `web/scripts` are mounted read-only for the final
run: the image does not otherwise include the latter two settings-test inputs.

- Initial focused run: 48 passed across authentication and observability tests.
- Completed observability tests: 18 passed, covering parser failures, stored
  session/account failures, rotation, reuse and family revocation, sanitized 401
  responses, fixed JSON log context, and authentication-material exclusion.
  Mocked re-reads cover missing/mismatched locked sessions and missing accounts
  without constructing invalid database rows. A failed transaction exit emits
  no generic rejection event and preserves the original runtime exception.
- Migration-first regression run: 36 passed across migration, observability,
  and settings tests. The first full run exposed migration tests disabling
  existing loggers via Alembic's `fileConfig`, plus the missing image inputs
  above (19 failed, 398 passed, 10 skipped). The new test module now temporarily
  enables its auth logger with automatic restoration. Runtime logging and
  migration code remain untouched.
- Final full `python -m pytest --tb=short -ra`: **417 passed, 10 skipped**, in
  524.36 seconds. The ten optional PostgreSQL spike tests require a separate
  `COURT4_SPIKE_DATABASE_URL`. One dependency deprecation warning concerns
  Starlette's use of HTTPX in TestClient.
- `python -m ruff check .`: passed.
- `python -m ruff format --check .`: passed, 382 files formatted.
- `python -m mypy app scripts tests`: five existing errors in
  `tests/test_source_media.py`, at lines 49, 58, 138, 287, and 295. Repeating the
  check with HEAD's auth service and excluding the new test file reproduced
  exactly these five errors (206 baseline versus 207 current source files).
  These unrelated errors were left unchanged.
- Final diff and whitespace review: passed; no changes staged.

The untracked `tatus --short` file was already present on resumption and contains
diff output. It is preserved separately from the intended three-file patch.
