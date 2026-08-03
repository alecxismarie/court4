# Phase 1.8C-B account verification and session security

## Policy

Court4 permits an active, unverified user to register, sign in, read their own
account, inspect existing private resources, sign out, and request another
verification message. A verified email is required by the centralized
`require_verified_user` dependency before `POST /api/v1/analyses`, including an
explicit Analyze Again request.

Migration `0005_account_security` deliberately leaves existing active accounts
unverified. There is no evidence that those addresses were previously validated.
Those users must verify before a new upload. Disabled bootstrap and legacy users
remain disabled and cannot authenticate. Existing ownership and resources are not
changed.

## Email boundary

Authentication depends on Court4's `AccountEmailService`, which in turn depends on
the provider-independent `EmailSender` protocol and `EmailMessage` model. Provider
SDK types must not cross this boundary. Messages have a recipient, Court4-owned
plain-text and HTML bodies, category, and correlation ID.

Development and test use a thread-safe in-memory sink. It records messages without
sending mail and logs only category and correlation ID. An authenticated user can
inspect only messages addressed to their own normalized address at
`GET /api/v1/auth/development/emails`. The endpoint is absent outside development
and test. The development backend and sink are rejected by staging/production
settings.

A production adapter must implement `EmailSender.send(EmailMessage) ->
DeliveryResult`, translate the provider result at the boundary, and avoid logging
message bodies or actionable links. `auth_email_backend=provider` is a fail-closed
configuration boundary until such an adapter is installed. Delivery failure is
reduced to a safe category and does not expose provider details through an API.

## Token lifecycle

Email verification and password reset use independent opaque tokens generated with
`secrets.token_urlsafe(48)`. Only SHA-256 exact-lookup hashes are persisted. Tokens
are purpose-bound, URL-safe, configurable-lived, and have creation, expiration,
consumption, and invalidation state. A partial unique index permits at most one
active token per user and purpose.

The raw token exists only long enough to construct a URL from the validated
`auth_frontend_base_url`; it is URL encoded and passed to the email boundary. It is
never returned by a production account API or written to a log.

Verification and reset acquire a PostgreSQL transaction-scoped advisory lock for
the account, then row locks. This serializes token replacement, consumption,
password mutation, login, refresh rotation, and revoke-all for one user. Concurrent
consumption succeeds at most once. Resend or a newer recovery request invalidates
the previous active token.

Default lifetimes:

- verification: 24 hours;
- password reset: 45 minutes.

## Recovery and password changes

`POST /api/v1/auth/forgot-password` returns the identical body and status for known,
unknown, malformed, disabled, and ineligible accounts. Only an active account gets
a token and email.

A valid reset transaction changes the Argon2id hash, records
`password_changed_at`, consumes the token, invalidates other reset tokens, and
revokes all refresh sessions. A password-changed notice is attempted after commit.
The user signs in again with the new password.

Authenticated password change requires the current password and a valid current
refresh cookie. Court4 rejects the same password, updates the hash, invalidates
recovery tokens, revokes every other refresh session, and rotates the current
refresh session. The current device stays signed in. This decision avoids
surprising the user who just reauthenticated while removing every other
long-lived credential.

## Sessions

`GET /api/v1/auth/sessions` returns only the owner's active, unexpired sessions:
ID, creation/last-use/expiry times, current flag, and a coarse browser/platform
label. It never returns token hashes, raw tokens, IP addresses, or the full user
agent.

`DELETE /api/v1/auth/sessions/{id}` is owner-scoped. Revoking the current session
also clears its cookie. `POST /api/v1/auth/sessions/revoke-all` accepts
`preserve_current_session`; preserving rotates the current session, while revoking
it clears the cookie. Revoke-all is idempotent and reports a safe count.

## API and frontend

Account endpoints under `/api/v1/auth` are:

- `POST /verify-email`
- `POST /resend-verification`
- `POST /forgot-password`
- `POST /reset-password`
- `POST /change-password`
- `GET /sessions`
- `DELETE /sessions/{session_id}`
- `POST /sessions/revoke-all`

Registration routes to a verification-pending page. Public verification, forgot,
and reset pages show typed expiry/consumption errors without provider information.
Settings contains email status, password change, active sessions, individual
revocation, and revoke-other controls. The upload page guides an unverified user to
verification; the API remains the authoritative enforcement layer. Access tokens
remain memory-only and email tokens are never placed in browser storage.

## Configuration

All variables use the `PICKLEBALL_AI_` prefix:

| Setting | Default |
| --- | --- |
| `AUTH_FRONTEND_BASE_URL` | `http://localhost:3000` |
| `AUTH_EMAIL_BACKEND` | `development` |
| `AUTH_DEVELOPMENT_EMAIL_SINK_ENABLED` | `true` |
| `AUTH_VERIFICATION_TOKEN_HOURS` | `24` |
| `AUTH_PASSWORD_RESET_TOKEN_MINUTES` | `45` |
| `AUTH_RESEND_VERIFICATION_RATE_LIMIT` | `3` |
| `AUTH_FORGOT_PASSWORD_RATE_LIMIT` | `5` |
| `AUTH_RESET_PASSWORD_RATE_LIMIT` | `10` |
| `AUTH_CHANGE_PASSWORD_RATE_LIMIT` | `5` |
| `AUTH_SESSION_ACTION_RATE_LIMIT` | `10` |

The frontend base must be an absolute HTTP(S) URL without credentials, query, or
fragment. Staging and production require HTTPS, a provider backend, and the
development sink disabled.

## Local testing

Run the API in development, register, then call the authenticated development-email
endpoint to inspect the message and link. Tests clear this sink between cases. The
PostgreSQL suite exercises token replay, expiry, concurrent consumption, reset
races with login/refresh, and revoke-all racing refresh.

## Logging and abuse controls

Security logs contain account IDs where already authenticated, action categories,
safe counts, and correlation IDs. They exclude passwords, access/refresh/email
tokens, and email bodies. Resend, forgot, reset, change-password, and session
mutations use focused limits.

The limiter is process-local and keyed primarily by operation and client address;
it is a pre-production limitation. Shared/distributed rate limiting, richer
delivery suppression, durable mail queues, and production email operations are
deferred to Phase 1.8E.

## Deferred scope

Phase 1.8D remains the private object-storage and data-lifecycle phase. Phase 1.8E
remains deployment and operational hardening. Social login, magic links, SMS,
MFA, billing, Redis, and unrelated analytics are not part of this implementation.
