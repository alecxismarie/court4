# Phase 1.8C-A authentication foundation

## Architecture

Court4 uses short-lived HS256 access tokens and rotating opaque refresh tokens. The
frontend keeps its access token only in JavaScript memory. A refresh token is a
cryptographically random value held in an `HttpOnly` cookie; PostgreSQL stores only
its SHA-256 digest. Each refresh row has an individual session UUID and token-family
UUID so rotation, logout, security revocation, and reuse response remain auditable.

Access tokens contain a user UUID, issuer, audience, issue/expiry times, and a unique
token ID. The API resolves the user on every protected request and rejects missing,
deleted, or disabled accounts. The access-token signing secret must be deployment
specific and is rejected in staging/production when left at its development value.

## Password and email policy

Passwords use Argon2id through `argon2-cffi`, including library-generated salts and
constant-time verification. A successful login upgrades an outdated hash. Passwords
must be 12–256 characters by default; Court4 imposes no composition rules.

Email normalization trims whitespace and Unicode case-folds the complete address.
It does not remove dots, plus tags, or otherwise apply provider-specific rules. The
normalized value has a database uniqueness constraint.

## Session lifecycle

Registration and login create a refresh session and return a ten-minute access token.
Refresh locks the current session row, marks it rotated, creates a successor in the
same family, and returns a new access token. Reuse of a rotated refresh token revokes
every still-live session in its family. Expired, revoked, malformed, disabled-account,
and mismatched tokens fail closed. Logout revokes the presented session and is
idempotent. Session rows can be revoked by user/family for future password or account
security actions; the password-change UI remains Phase 1.8C-B scope.

## Cookies, CSRF, and CORS

The refresh cookie is `HttpOnly`, explicitly expires, and is restricted to
`/api/v1/auth`. Production/staging default to `Secure`; plain-HTTP development can
set `PICKLEBALL_AI_AUTH_COOKIE_SECURE=false`. `SameSite=lax` is the default.

Refresh and logout require an exact `Origin` match from
`PICKLEBALL_AI_FRONTEND_ALLOWED_ORIGINS`. Credentialed CORS uses that exact list and
rejects wildcard configuration. This combines SameSite cookie behavior with explicit
origin validation for cookie-authenticated state changes.

## Ownership enforcement

All `/api/v1/analyses/**` and `/api/v1/play-history` requests depend on the single
`get_current_user` mechanism. Request-scoped workflows receive that user's UUID.
The client cannot choose `owner_user_id`. Persistence queries and composite foreign
keys continue to enforce ownership for uploads, duplicate checks, analyses, runs,
artifacts, selections, and history. Cross-owner and missing objects both return the
existing 404 response to avoid resource enumeration.

Health, readiness, OpenAPI, and internal calibration-readiness contain no private
user resources and remain public.

## Development bootstrap and existing data

Bootstrap is disabled by default and the HTTP authentication dependency never uses
it. An explicitly enabled non-production bootstrap may support compatibility tools
and legacy tests only; its account is disabled and has an unusable password marker.
Production configuration rejects bootstrap activation.

The migration preserves existing users and ownership links. Legacy identity labels
become normalized emails, receive an unusable password marker, and are not attached
to newly registered accounts. No automatic claim or reassignment occurs. A future
claim workflow requires an explicit product and security policy.

The pre-migration local production inventory on 2026-07-31 contained one explicit
development bootstrap user owning three uploaded videos, three analyses, three runs,
663 artifact records, and three idempotency records; it had no player-selection
records. Migration disables that legacy account while retaining every ownership
foreign key. These records therefore remain preserved but inaccessible through
normal authentication until an explicit claim/import policy is approved.

## Environment and local testing

Authentication settings use the `PICKLEBALL_AI_AUTH_*` variables documented in
`.env.example`. At minimum, production must provide a strong unique
`AUTH_ACCESS_TOKEN_SECRET`, HTTPS-compatible cookie security, and the exact frontend
origin list.

Apply migrations with `alembic upgrade head`, start the API and frontend, register,
then use the returned in-memory access token through the frontend client. Direct
refresh/logout smoke requests must send an allowed `Origin` header.

## Abuse protection and observability

Registration, login, and refresh have focused per-process/IP rate limits. Security
events record categories and user/session identifiers but never passwords, raw
tokens, or cookies. A distributed deployment should replace the process-local
limiter with a shared Redis or gateway limiter before horizontal scaling.

## Phase 1.8C-B

Deferred work includes email verification and delivery, forgot/reset/change
password flows, revoke-all-sessions UI, and any provider login. Google, Apple,
administrator roles, subscriptions, billing, storage, and deployment are outside
this phase.
