# Mandatory email verification policy

Court4 accounts exist immediately after registration, but product access is not activated until `email_verified_at` is present. Authentication alone is not authorization to enter the private application.

## Route policy

An authenticated, active, unverified account may use only session restoration (`/auth/me`, refresh), logout, verification resend and completion, the isolated test-only development email sink, and public password recovery. It may not use Dashboard data, analyses, uploads, duplicate detection, re-analysis, history, Play History, calibration, tracking, player discovery or selection, analytics, private artifacts, onboarding, password changes, managed-session settings, Player Workspace, or any other private product resource.

All `/analyses` routes, including development analysis routes, resolve their owner-scoped workflow through `VerifiedUser`. `/play-history` does the same. Verified-only auth operations use the same central dependency. `require_verified_user` first requires normal authentication, retains the active-account check, requires `email_verified_at`, and returns HTTP 403 with the typed `email_verification_required` error. Ownership checks remain downstream and unchanged. The frontend is not the security boundary.

The explicit unverified exceptions are:

- `POST /auth/register` and `POST /auth/login`, which establish the existing provisional session;
- `POST /auth/refresh` and `GET /auth/me`, so another-browser verification can be observed safely;
- `POST /auth/logout`;
- `POST /auth/resend-verification` and `POST /auth/verify-email`;
- forgot/reset password routes;
- `/auth/development/emails` only in development/test with the development sink enabled.

## Frontend gate and navigation

The global authenticated boundary waits for session restoration before rendering private content. An active unverified session requesting any private path is sent to `/verification-pending`; private content and private navigation are withheld during loading and redirect. `/verification-pending` is the only provisional-account application page. A verified account that reaches it is sent to `/dashboard`, preventing loops.

The policy intentionally discards a pre-verification private `next` destination. First-account activation always continues through Dashboard so the persisted “What should we call you?” onboarding step occurs before normal navigation. Login preserves a validated internal destination only for accounts already verified.

“Use a different email” implements the narrow safe fallback: Court4 logs out, clears in-memory credentials, and returns to the landing-page Sign Up tab without persisting the previous email. No duplicate account is created silently and the account/email model is not broadened.

## Verification and onboarding sequence

Registration creates the account, sends the verification message, keeps the existing provisional session, and immediately opens `/verification-pending`. The pending page can resend and can refresh `/auth/me` through the existing session when the user selects “I’ve verified my email.” The frontend never supplies or changes verification status.

The first valid token consumption retains the existing hashed, expiring, single-use token transaction and verification-session handoff. It marks `email_verified_at`, invalidates sibling tokens, creates or rotates the normal refresh session, returns an in-memory access token, removes the token from the visible URL, and opens `/dashboard`. Dashboard alone presents onboarding while `display_name` is unset; `/auth/onboarding` is verified-only and persists completion.

Disabled accounts cannot resolve authenticated dependencies or consume verification tokens. Expired and consumed links retain their typed safe responses. Verification in another browser activates the account; the original browser discovers it only by a server-backed session/user refresh.

## Validation results (2026-08-04)

- Focused backend authentication, settings, and history run: 56 passed.
- Full backend suite: passed; 10 repository tests were intentionally skipped by their existing markers/environment requirements.
- Ruff check and Ruff format check: passed. Mypy: passed across 154 source files.
- Alembic check: no new upgrade operations detected.
- Full frontend suite: 181 passed across 37 files. ESLint and TypeScript: passed. Next.js production build: passed.
- Focused real Chrome flow: 6 passed. It covers registration, manual private-route rejection, hidden private navigation, real development-sink token consumption, Dashboard onboarding and persistence, post-verification upload access, another-browser verification and original-browser refresh, replay refusal, account mismatch, unverified login/logout, mobile overflow, and browser console collection.
- Runtime API flow: `/health` returned `ok`; `/ready`, registration, `/auth/me`, verified analysis listing, and onboarding returned success. Analysis listing before verification returned HTTP 403 with `email_verification_required`; the same route returned HTTP 200 immediately after real verification.

Expired-token behavior passed backend and component coverage. The focused browser run did not mutate the database clock/token expiry, so expiry was not re-proven as a real browser scenario. External-provider inbox delivery was not invoked and remains a separate manual release gate.

## Test email safety

`ENVIRONMENT=test` defaults to `EMAIL_PROVIDER=development` and requires the development sink. Selecting Brevo or Resend fails settings validation unless `ALLOW_EXTERNAL_EMAIL_IN_TESTS=true` is explicitly provided. Normal test bootstrap pins the development provider before the repository `.env` is read. Provider-adapter tests use the opt-in only with isolated mock transports; real delivery remains a separate manual validation.
