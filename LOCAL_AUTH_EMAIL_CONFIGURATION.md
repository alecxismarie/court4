# Court4 local auth and email configuration

This correction is local/runtime configuration work only. It does not deploy Court4.

## Canonical origins

Use exactly this pair for normal local development:

```text
Frontend: http://localhost:3000
Backend:  http://localhost:8000
```

Do not open one service through `127.0.0.1` while the other uses `localhost`.
Refresh cookies are host-only, and browsers treat those names as different hosts.
The backend also uses the one configured frontend origin for credentialed CORS and
Origin-based CSRF checks. A mixed origin is intentionally rejected.

The same code supports staging through configuration:

```dotenv
FRONTEND_BASE_URL=https://court4.lexora.ltd
PICKLEBALL_AI_FRONTEND_ALLOWED_ORIGINS=https://court4.lexora.ltd
NEXT_PUBLIC_COURT4_API_URL=https://api.court4.lexora.ltd
PICKLEBALL_AI_AUTH_COOKIE_SECURE=true
PICKLEBALL_AI_AUTH_COOKIE_SAMESITE=lax
```

Staging and production require HTTPS, a Secure refresh cookie, and exactly one
allowed frontend origin. No localhost fallback or wildcard is added.

## Local setup

`.env.example` is documentation only. Copy it to the ignored root `.env`, then edit
only `.env`. Compose requires that runtime file and never loads `.env.example`:

```powershell
Copy-Item .env.example .env
```

For the local development sink, keep these values:

```dotenv
PICKLEBALL_AI_ENVIRONMENT=development
PICKLEBALL_AI_FRONTEND_ALLOWED_ORIGINS=http://localhost:3000
FRONTEND_BASE_URL=http://localhost:3000
EMAIL_PROVIDER=development
PICKLEBALL_AI_AUTH_DEVELOPMENT_EMAIL_SINK_ENABLED=true
EMAIL_FROM_ADDRESS=court4@localhost.invalid
BREVO_API_KEY=
RESEND_API_KEY=
```

Set the ignored `web/.env.local` to:

```dotenv
NEXT_PUBLIC_COURT4_API_URL=http://localhost:8000
NEXT_PUBLIC_COURT4_MAX_UPLOAD_BYTES=1073741824
NEXT_PUBLIC_COURT4_SUPPORTED_VIDEO_EXTENSIONS=.mp4,.mov,.avi,.mkv
```

Then start the backend and frontend normally, or start the backend with
`docker compose up --build api postgres`. Missing `.env`, invalid selected-provider
credentials, mismatched origins, and unsafe deployment cookie settings fail clearly.

## Delivery wording and development inbox

Successful delivery is classified without exposing a provider name:

- `development`: the message was recorded in the in-memory local sink;
- `external`: the configured external provider accepted the message;
- `unavailable`: no success wording may be shown.

The verification-pending page says "captured in the local development inbox" for
the sink and "sent" only after accepted external delivery. Registration still rolls
back when its verification delivery fails. Resend returns a typed failure and no
success copy when delivery fails.

The development inbox endpoint is `/api/v1/auth/development/emails`. It requires the
provisional user's bearer token and is mounted only in development/test with the
development provider and sink enabled. It is absent from staging/production.

## Session consistency and resend recovery

Access tokens remain memory-only. A conclusive refresh `401` clears the access
token, user/email, verification/profile state, and pending onboarding markers through
one auth-context reset. Network errors, rate limiting, and server/provider
unavailability do not clear a displayed user under the existing error policy.

Authenticated account actions such as resend verification may recover once through
the HttpOnly refresh cookie. Public credential, recovery, refresh, and verification-
token consumption endpoints remain excluded. The original request is retried once;
there is no recursive refresh or second resend retry.

"Check verification status" refreshes server-backed session/user state and inspects
`email_verified_at`. It does not verify an account or consume a token.

## Isolated tests

Normal tests force `EMAIL_PROVIDER=development`, blank both external API key
variables before Settings loads the root environment, and reject external providers
unless a specific mock-transport test opts in. The `api-test` Compose service has no
`env_file`; it supplies a disposable database identity, isolated signing secret,
development sink, and blank provider keys explicitly.

For E2E on port 3002, set `COURT4_TEST_FRONTEND_ORIGIN=http://localhost:3002` when
starting `api-test`. The sequential browser suite may set
`COURT4_TEST_AUTH_REGISTER_RATE_LIMIT=100`; the default remains `5` so backend
rate-limit tests exercise the release policy. Automated tests never call Brevo.

## Optional manual Brevo validation

Do this only in a separate, explicitly authorized manual run with an approved test
recipient. Update the ignored root `.env`:

```dotenv
EMAIL_PROVIDER=brevo
BREVO_API_KEY=<local Brevo HTTP API key>
EMAIL_FROM_ADDRESS=<verified sender>
EMAIL_FROM_NAME=Court4
FRONTEND_BASE_URL=http://localhost:3000
PICKLEBALL_AI_FRONTEND_ALLOWED_ORIGINS=http://localhost:3000
```

Keep `web/.env.local` on `http://localhost:8000`. Restart both services, then prove
in a real inbox: registration receipt and link consumption, one resend receipt,
password-reset receipt, and reset-link consumption. Record sanitized timestamps and
message identifiers only. Do not record credentials or actionable links. Mocked
adapter tests and HTTP success alone are not proof of real delivery.

## Future session-persistence enhancement

Court4 currently uses one configured secure refresh-session lifetime. The login UI
does not offer "Remember Me" or "Keep Me Signed In" because no separate browser-
session versus persistent-session policy exists. A future product task may add an
explicit, tested persistence choice; this release does not change session duration,
rotation, revocation, or cookie behavior.
