# Authentication Direction

## Separation of concerns

- **Authentication** establishes the user and session.
- **Registration eligibility** decides whether a new account may be created during
  private alpha.
- **Authorization** decides whether the authenticated actor may perform an action.
- **Ownership** is durable resource data (`owner_user_id`), not a token claim alone.

Disabling open registration must not change login or ownership semantics.

## Recommendation

Use a managed authentication service with a local Court4 `users` row and
`auth_identities(provider, provider_subject)` mapping. Supabase Auth is the preferred
private-alpha candidate, subject to a Phase 1.8C integration spike; the architectural
contract is standards-based JWT/JWKS validation and does not make Supabase IDs the
primary keys of Court4 resources.

Permanent flows are email/password registration, email verification, login, logout,
forgot password, reset, and password change. Google and Apple identities may be
linked later. Magic links may be an optional recovery/convenience feature, not the
only login method.

Next.js should establish/refresh the provider session using secure, `HttpOnly`,
`Secure`, `SameSite=Lax` cookies. FastAPI validates issuer, audience, signature,
expiry, not-before time, and stable subject against cached JWKS, then resolves the
local active user. Authorization always queries ownership from PostgreSQL.

## Option comparison

| Direction | FastAPI / Next.js fit | Account features | Lock-in / operations | Verdict |
| --- | --- | --- | --- | --- |
| Supabase Auth + local mapping | Good SDK/SSR support; FastAPI can validate JWT via JWKS | Email/password, verification, reset, Google/Apple | Moderate vendor coupling; exportable local mapping; low alpha operations | Preferred candidate |
| General external IdP (Auth0, Clerk, Cognito) | Strong OIDC/JWKS integration; SDK quality varies | Usually complete | Higher cost or configuration; UI/session coupling | Viable fallback |
| Self-managed credentials and sessions | Native control in Python/DB; more Next.js integration work | Must implement every flow safely | Lowest vendor lock-in, highest security and email burden | Not recommended for alpha |
| Supabase database plus Auth as one platform | Simple low-cost topology | Complete enough | Couples database and auth operationally | Acceptable hosting choice, not a domain-model requirement |

Provider selection criteria:

- stable subject identifiers and signed tokens usable by FastAPI;
- email/password, verification, reset, logout-all, and account disable/delete APIs;
- future Google and Apple linking without duplicate local users;
- safe SSR cookie guidance for Next.js;
- configurable redirect allowlists and anti-enumeration behavior;
- exportability, audit logs, availability, regional/data-location fit, cost, and
  private-alpha registration hooks.

## Local identity mapping

On a validated token:

1. look up `(issuer/provider, subject)` in `auth_identities`;
2. load `users` and reject disabled, suspended, deletion-pending, or deleted states;
3. attach `{user_id, session_id, account_status, actor_type}` to request context;
4. never trust email as the ownership key;
5. reconcile verified-email changes through an explicit identity update flow.

Linking Google or Apple later requires a recently authenticated session and proof of
the new provider identity. Email equality alone must not auto-link identities.

## Session and request security

- Access tokens are short-lived; refresh tokens remain in secure provider-managed
  cookies and are never exposed to browser JavaScript or FastAPI logs.
- If cookie credentials reach FastAPI directly, state-changing requests require
  CSRF protection (same-origin BFF plus origin checks and CSRF token). A bearer
  access token set by the Next.js server avoids browser-readable tokens.
- Rotate session identifiers after login, verification, password reset, and privilege
  change. Revoke all sessions after password reset or account suspension.
- Hash local provider-session identifiers and reset/verification tokens.
- Apply uniform registration/reset responses to reduce account enumeration.
- Rate-limit registration, login, resend verification, forgot-password, and reset by
  IP prefix plus normalized account key.

## Account-state policy

Unverified users may authenticate only into a restricted verification session. They
may resend verification, log out, correct their email through a verified flow, and
delete the pending account. They may not upload, start analyses, access histories,
download artifacts, or submit normal feedback.

`active` verified users have normal owner capabilities. `disabled` is a reversible
user choice or operational state; `suspended` is an administrative security state.
Both block new sessions and resource access except account/support flows explicitly
approved by policy. `deletion_pending` permits cancellation during the cooling-off
period and data export if offered; it blocks uploads and processing.

## Complete account lifecycle

1. **Registration request:** normalize email, apply anti-abuse controls, evaluate the
   separate alpha policy, and return a non-enumerating response.
2. **Account creation:** create managed-auth identity, local `User` in
   `pending_verification`, empty PlayerProfile, required agreement acceptance, and
   an audit event in a compensating/idempotent workflow.
3. **Verification:** consume a single-use expiring token, set provider/local
   verification state, activate the user, rotate any restricted session, and record
   the event.
4. **Authentication/session:** provider verifies credentials; Next.js establishes a
   secure session; FastAPI maps the subject to the active local user. `last_seen_at`
   updates are throttled rather than written on every request.
5. **Logout:** revoke the current provider session and local session ledger entry;
   response is idempotent.
6. **Forgot/reset password:** always return a generic request response; consume a
   one-time token, change the credential, revoke all sessions, notify the account,
   and audit without logging the token.
7. **Password change:** require recent authentication and current password/provider
   proof, rotate credentials and sessions, and notify the account.
8. **Disabled:** deny new login and normal resource access. Re-enable only through
   the defined self-service or administrator recovery policy.
9. **Suspended:** administrator/security state; revoke sessions immediately, deny
   normal access, require a reason and audit trail.
10. **Deletion pending:** require recent authentication, revoke normal sessions,
    block new work, preserve only cancellation/export/support access during the
    cooling period, and start the deletion state machine.
11. **Deletion completed:** active resources and private objects are reconciled as
    deleted, provider identity is removed/disabled, local user is tombstoned or
    purged according to approved audit/re-registration policy, and backup expiration
    proceeds under the retention schedule.

Email change is a verified identity operation: verify the new address, maintain the
old address until confirmation, update provider and local mapping idempotently, and
notify both addresses. Billing later consumes account-state events but does not own
account lifecycle.

## Private-alpha registration

Use an approved-email allowlist plus a global registration toggle:

- entries are administrator-created, single-email, expiring, auditable, and
  single-use after successful account creation;
- the registration endpoint returns a uniform response regardless of eligibility;
- there is no reusable shared access code;
- existing users continue to authenticate when registration is disabled;
- removing the eligibility check opens public registration without identity or
  schema changes.

Administrator approval after account creation adds unnecessary pending accounts and
support work. Registration windows are less controllable. Shared codes leak and are
not recommended.

## Phase 1.8C spike acceptance

Before provider commitment, demonstrate registration restriction, verification,
password reset, SSR session refresh, FastAPI JWKS validation, logout/revocation,
account disable/delete, local mapping, key rotation, and one simulated future
provider link. Record provider-specific decisions in a follow-up ADR.
