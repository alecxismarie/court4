# Phase 1.8C-A validation report

## Audit findings

- `users` previously held UUID, unique `identity_label`, status, and timestamps;
  there was no password or session model.
- `get_persistence()` previously required an explicit bootstrap identity and exposed
  one process-wide `owner_user_id`.
- `AnalysisJobRepository` used that owner for uploads, exact-duplicate detection,
  analyses, artifacts, runs, player selection, analytics, and derived histories.
- The owner-filtered PostgreSQL service and composite owner foreign keys already
  failed cross-owner lookups as not found.
- The private API surface is `/api/v1/analyses/**` and `/api/v1/play-history`.
  Health/readiness and internal calibration readiness are not user-owned.
- The frontend had centralized JSON helpers plus a separate upload XHR, React Query,
  exact-origin credentials-disabled CORS, Pydantic environment settings, and no
  authentication or rate-limit utilities.

## Selected architecture

Court4 now uses short-lived signed bearer access tokens plus individually revocable,
rotating opaque refresh sessions. Access tokens remain in frontend memory. Refresh
tokens live only in an `HttpOnly` cookie and are stored in PostgreSQL as SHA-256
digests. Rotation is serialized with a row lock; token-family reuse revokes the
family. Argon2id protects passwords and upgrades hashes after successful login.

This fits the separate Next.js/FastAPI topology without exposing a long-lived token
to JavaScript or local storage.

## Database

Migration `0004_authentication_foundation`:

- renames normalized `identity_label` to `email`;
- adds `password_hash` and `last_login_at`;
- preserves and disables pre-authentication users with an unusable password marker;
- adds `refresh_sessions` with user/family/expiry indexes, hashed token uniqueness,
  rotation link, timestamps, revocation metadata, and client user agent.

The existing local production inventory was one bootstrap user owning three videos,
three analyses, three runs, 663 artifacts, and three idempotency records. No records
were reassigned or attached to a new registrant.

## API contract

- `POST /api/v1/auth/register` — creates an account/session, returns safe user plus
  short-lived access token, and sets the refresh cookie.
- `POST /api/v1/auth/login` — generic invalid-credential response, upgrades password
  hash when needed, records last login, and creates a session.
- `POST /api/v1/auth/refresh` — validates and rotates the cookie session.
- `POST /api/v1/auth/logout` — idempotently revokes the active session and clears the
  cookie.
- `GET /api/v1/auth/me` — resolves the bearer token through `get_current_user`.

No response exposes password hashes, refresh tokens, or internal session fields.

## Cookie, CSRF, and CORS behavior

The refresh cookie is `HttpOnly`, path-limited to `/api/v1/auth`, explicitly
expiring, and `SameSite=lax` by default. Secure cookies are mandatory in staging and
production; local HTTP may explicitly disable `Secure`. Refresh and logout require
an exact allowed `Origin`. Credentialed CORS uses only the configured exact origins;
wildcards are rejected.

## Ownership cutover

Every analysis and play-history dependency now receives the authenticated user's
UUID. Client ownership identifiers are never accepted as authority. Upload,
duplicate detection, reanalysis, all workflow stages, selection, analytics,
artifacts, private share-card artifacts, and histories retain their persistence
owner predicates. Missing and cross-owner resources both return 404.

Bootstrap remains an explicit, default-off, non-production compatibility mechanism.
It is not consulted by normal authenticated HTTP routes.

## Frontend

The frontend now has a typed auth client, memory token store, coordinated refresh,
registration/login pages, auth provider, initial current-user restoration, protected
route redirect with intended destination, logout, and session clearing. Upload XHR
requests carry bearer auth and retry once after refresh. Private images are fetched
as authenticated blobs; share-card proxy requests forward bearer authorization.
No authentication token or password is written to local storage.

## Validation

- Alembic upgrade: passed.
- Alembic downgrade and re-upgrade: passed twice, including the finalized legacy
  disable policy.
- `alembic check`: passed, no upgrade operations detected.
- Full backend suite: 216 collected; 206 passed and 10 optional spike tests skipped.
- Focused auth/authorization/concurrency suite: 11 passed.
- Ruff: passed.
- Mypy: passed across 134 source files.
- Frontend tests: 117 passed across 23 files.
- Frontend lint: passed with no warnings.
- Frontend type-check: passed.
- Frontend production build: passed.
- Live smoke: register, login, me, upload, duplicate, Analyze Again, analysis
  retrieval, analysis history, play history, logout, unauthenticated rejection,
  cross-user rejection, expired access token, and refresh after expiry all passed.

## Remaining risks and Phase 1.8C-B readiness

- The focused auth limiter is process-local; multi-instance production needs a
  shared gateway/Redis limiter.
- HS256 secret rotation and refresh-session cleanup need operational runbooks.
- Legacy bootstrap data is intentionally inaccessible until an explicit claim/import
  policy is approved.
- There are currently no public run-ID, upload-ID, or player-selection-ID routes;
  their persistence operations remain owner-filtered, but direct HTTP substitution
  tests become applicable when such routes are added.
- The suite reports an upstream Starlette `TestClient`/httpx deprecation warning;
  it does not affect runtime authentication.

The foundation is ready for Phase 1.8C-B email verification, forgot/reset/change
password flows, verification delivery, and revoke-all-sessions UI. Social login,
billing, storage, and deployment remain deferred.
