# Verification-session handoff

## Final flow

Court4 now uses one continuous account flow:

1. The landing-page Sign Up panel registers the account and creates the existing normal Court4 session.
2. Court4 sends a one-time email-verification link.
3. `POST /api/v1/auth/verify-email` validates and atomically consumes that token.
4. The endpoint marks the email verified, creates or rotates a normal refresh session, sets the existing HttpOnly refresh cookie, and returns the normal short-lived access-token response.
5. The frontend keeps the access token in memory, removes the verification token from the visible URL, and redirects to `/dashboard`.
6. Dashboard opens the “What should we call you?” dialog while the persisted `display_name` is unset.
7. `POST /api/v1/auth/onboarding` persists the name. Refreshes and other devices then recognize onboarding as complete.

No OTP, reusable magic-login token, second auth provider, or second session type was added.

## Security and transaction design

Verification tokens remain 48-byte URL-safe random values. Only their SHA-256 hashes are stored in `account_tokens`. The existing purpose, expiry, consumed, and invalidated checks remain mandatory.

Verification uses the existing per-user PostgreSQL advisory transaction lock and a row lock on the account token. Token consumption, the verified timestamp, invalidation of sibling verification tokens, and refresh-session creation or rotation commit in one transaction. Two concurrent consumers therefore produce one authenticated session and one typed `invalid_or_used_token` failure.

If the browser already has an active refresh session for the same user, verification rotates that session in its existing token family instead of creating an unnecessary parallel session. A browser without a session receives a new normal refresh session. Refresh hashing, expiry, rotation, reuse detection, revocation, cookie attributes, CORS, CSRF-origin checks on cookie actions, and access-token behavior are unchanged.

The raw verification token is never returned after consumption, written to storage, or logged. Safe events record verification success, session establishment, replay/invalid rejection, account mismatch, and onboarding completion without credentials or URLs.

## Edge-case contract

| Case | Behavior |
|---|---|
| Valid token, unverified active user | Verify, consume once, establish/rotate session, redirect to Dashboard |
| First valid consumption on another browser | Establish a normal session in that browser and redirect to Dashboard |
| Consumed token | Return `invalid_or_used_token`; never create another session |
| Expired token | Return `token_expired`; never authenticate; offer resend guidance |
| Invalid or malformed token | Return the generic `invalid_or_used_token` response |
| Disabled or missing user | Fail with the generic invalid-token response and create no session |
| Already-verified user with an unconsumed valid token | Consume that first valid token and establish/rotate the normal session |
| Already-verified user replaying a consumed token | Reject replay; the old link is never a reusable login mechanism |
| Different authenticated user in the browser | Return `verification_account_mismatch` without consuming the token; require explicit logout before retry |

## Auth-route consolidation

The designed landing page remains the public authentication surface:

- `/login` redirects to `/?auth=login`.
- `/register` redirects to `/?auth=signup`.
- A validated internal `next` destination is preserved.
- External, protocol-style, backslash, protocol-relative, and auth-loop destinations are discarded.
- Authenticated verified visitors to `/` continue to the validated destination or Dashboard.
- Authenticated unverified visitors to `/` go to `/verification-pending`.
- Session restoration completes before public auth content or redirects are shown.

Forgot-password, reset-password, verification-pending, and verification routes remain dedicated routes.

## Onboarding persistence

Migration `0006_auth_onboarding` adds nullable `users.display_name`. A null value is the durable first-time-onboarding state. Saving the required name updates the backend user and then the account-scoped browser profile. On another browser, the backend name hydrates the local profile and prevents the dialog from reopening.

Known focused-scope limitation: the Player page’s optional profile fields, photo, and later browser-local display-name edits remain local. This remediation persists the first-time onboarding name and completion state only; it does not build broader server-backed profile editing.

## Validation coverage

Backend coverage includes normal session/cookie issuance, same-session rotation, different-browser establishment, replay, expiry, malformed tokens, disabled users, mismatch refusal, concurrent one-winner consumption, security-event counts, refresh rotation, logout, password-reset revocation, and cross-context onboarding persistence.

Frontend coverage includes auth-context adoption, automatic Dashboard redirect, token URL removal, expired/replay/mismatch UI, no browser token persistence, durable-name hydration, modal completion, tab selection, route consolidation, safe `next`, session-restoration flicker prevention, and protected-route behavior.

Real PostgreSQL browser coverage exercises the same-browser flow, different-browser flow, replay in a third context, different-user mismatch, `/login` and `/register` consolidation, refresh persistence, logout, and console scanning after the authenticated handoff.
