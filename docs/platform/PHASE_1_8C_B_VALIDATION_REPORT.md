# Phase 1.8C-B validation report

Validation completed on 2026-07-31 against PostgreSQL 16, Python 3.12 in the
Court4 image, and the Next.js production build.

## Database

- Upgraded isolated test database from `0004_authentication_foundation` to
  `0005_account_security`.
- Downgraded `0005` back to `0004`, then re-upgraded to `0005`.
- `alembic check`: `No new upgrade operations detected.`
- Upgraded the existing local production database to `0005`.
- Preservation counts before/after remained 1 user, 3 videos, 3 analyses, and
  663 artifacts. The existing user remains disabled; account-token count was zero
  immediately after migration.

## Backend

- Focused authentication/account-security suite: 24 passed.
- Full backend suite: 229 collected; 219 passed and 10 optional integration tests
  skipped.
- Required PostgreSQL races cover double verification/reset consumption, reset
  racing login, reset racing refresh, revoke-all racing refresh, and concurrent
  resend replacement.
- Ruff: all checks passed.
- Mypy: no issues in 149 source files.

The only test warning is Starlette's upstream deprecation notice for the current
`httpx` TestClient integration.

## Frontend

- Vitest: 26 files, 126 tests passed.
- ESLint: no warnings or errors.
- TypeScript: no errors.
- Next.js production build: compiled and generated all 21 pages/routes.
- Targeted verification test rerun after the final signed-in refresh adjustment:
  2 passed.
- Both maintained Playwright smoke scripts pass JavaScript syntax checks.

## Live HTTP and browser smoke

The rebuilt API and production frontend were exercised with installed Chrome in
headless mode. The smoke covered:

- registration and post-registration verification notice;
- authenticated development-email sink inspection;
- resend replacing the first verification link;
- unverified upload returning `email_verification_required`;
- verification and downstream upload-policy unlock;
- consumed verification-link rejection;
- equivalent known/unknown forgot-password UI;
- password reset and old refresh-session rejection;
- login with the reset password;
- authenticated password change with current-device rotation;
- other-session rejection after password change;
- session listing and revoke-all-other behavior;
- logout;
- a database-expired synthetic reset token showing the typed expired-link UI.

Synthetic smoke users, failed test-upload metadata, and artifacts were removed
afterward. Original local production counts were rechecked and preserved. The API,
frontend helper, and local production database were stopped; the pre-existing
isolated test database was left running.

## Remaining risks

- Email delivery is provider neutral but no production provider adapter is
  installed. Deployment configuration fails closed.
- The development email sink is memory-only and intentionally unavailable in
  staging/production.
- Rate limiting is process-local, address-oriented, and not suitable for a
  multi-instance deployment.
- Revoking refresh sessions does not invalidate an already issued stateless access
  token; its maximum residual lifetime is the configured short access-token
  lifetime (10 minutes by default).
- Email delivery is synchronous and has no durable retry/outbox. Operational mail
  delivery belongs in Phase 1.8E.
- Object storage remains Phase 1.8D scope; deployment and operational jobs remain
  Phase 1.8E scope.

Phase 1.8C-B is complete for the local/pre-alpha platform contract. Court4 is ready
to begin Phase 1.8D without treating this result as production-deployment
readiness.
