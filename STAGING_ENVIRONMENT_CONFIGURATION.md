# Court4 staging environment configuration

This is a names-only template. Secrets belong in the deployment secret store, not Git. The example hostnames are placeholders until DNS and TLS are approved.

## Required staging template

```dotenv
PICKLEBALL_AI_ENVIRONMENT=staging
PICKLEBALL_AI_PERSISTENCE_BACKEND=postgresql
PICKLEBALL_AI_DATABASE_URL=
PICKLEBALL_AI_DATABASE_POOL_SIZE=10
PICKLEBALL_AI_DATABASE_MAX_OVERFLOW=10
PICKLEBALL_AI_DATABASE_POOL_TIMEOUT_SECONDS=10
PICKLEBALL_AI_DATABASE_POOL_RECYCLE_SECONDS=1800
PICKLEBALL_AI_DATABASE_POOL_PRE_PING=true
PICKLEBALL_AI_DATABASE_STATEMENT_TIMEOUT_MS=10000
PICKLEBALL_AI_DATABASE_LOCK_TIMEOUT_MS=5000
PICKLEBALL_AI_DATABASE_IDLE_TRANSACTION_TIMEOUT_MS=15000
PICKLEBALL_AI_ALLOW_DESTRUCTIVE_DATABASE_OPERATIONS=false

FRONTEND_BASE_URL=https://court4.lexora.ltd
NEXT_PUBLIC_COURT4_API_URL=https://api.court4.lexora.ltd
PICKLEBALL_AI_FRONTEND_ALLOWED_ORIGINS=https://court4.lexora.ltd

PICKLEBALL_AI_AUTH_ACCESS_TOKEN_SECRET=
PICKLEBALL_AI_AUTH_ACCESS_TOKEN_MINUTES=10
PICKLEBALL_AI_AUTH_REFRESH_TOKEN_DAYS=30
PICKLEBALL_AI_AUTH_REFRESH_COOKIE_NAME=court4_refresh
PICKLEBALL_AI_AUTH_COOKIE_SECURE=true
PICKLEBALL_AI_AUTH_COOKIE_SAMESITE=lax

REGISTRATION_ENABLED=true
PRIVATE_ALPHA_ALLOWLIST_ENABLED=true
PRIVATE_ALPHA_ALLOWED_EMAILS=

EMAIL_PROVIDER=brevo
BREVO_API_KEY=
EMAIL_FROM_ADDRESS=no-reply@lexora.ltd
EMAIL_FROM_NAME=Court4
PICKLEBALL_AI_AUTH_DEVELOPMENT_EMAIL_SINK_ENABLED=false
ALLOW_EXTERNAL_EMAIL_IN_TESTS=false

PICKLEBALL_AI_LOCAL_STORAGE_ROOT=/app/data/output
PICKLEBALL_AI_INPUT_DIR=/app/data/input
PICKLEBALL_AI_OUTPUT_DIR=/app/data/output
PICKLEBALL_AI_CALIBRATION_OUTPUT_DIR=/app/data/output
PICKLEBALL_AI_TRACKING_OUTPUT_DIR=/app/data/output
PICKLEBALL_AI_ANALYTICS_OUTPUT_DIR=/app/data/output
PICKLEBALL_AI_ANALYSIS_OUTPUT_DIR=/app/data/output
PICKLEBALL_AI_MAX_UPLOAD_SIZE_BYTES=536870912
NEXT_PUBLIC_COURT4_MAX_UPLOAD_BYTES=536870912
PICKLEBALL_AI_STORAGE_WARNING_FREE_BYTES=10737418240
PICKLEBALL_AI_STORAGE_HARD_STOP_FREE_BYTES=5368709120
PICKLEBALL_AI_STORAGE_UPLOAD_RESERVATION_MULTIPLIER=2.0
PICKLEBALL_AI_STORAGE_MAX_ACTIVE_UPLOADS=1
PICKLEBALL_AI_SUPPORTED_EXTENSIONS=.mp4,.mov,.avi,.mkv

PICKLEBALL_AI_BOOTSTRAP_USER_ENABLED=false
PICKLEBALL_AI_LEGACY_IMPORT_ENABLED=false
PICKLEBALL_AI_SOFTWARE_COMMIT_IDENTIFIER=
PICKLEBALL_AI_DEPLOYMENT_BUILD_IDENTIFIER=
PICKLEBALL_AI_PIPELINE_VERSION=court4-1.8b
PICKLEBALL_AI_DEFAULT_TRACKING_BACKEND=ultralytics
COURT4_DETECTOR_MODEL_PATH=/app/models/yolo11n.pt
COURT4_DETECTOR_MODEL_SHA256=0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1
BALL_TRACKING_ENABLED=false
```

Provision the detector volume from the exact release image before starting the API:

```bash
python -m scripts.provision_detector_model --destination /app/models/yolo11n.pt
```

The command retrieves only the pinned Ultralytics assets `v8.3.0` artifact and
refuses to install bytes that do not match the committed checksum. Mount the
provisioned model volume read-only in the API service. When the default tracking
backend is `ultralytics`, API startup fails if the model is absent or invalid. See
`DETECTOR_MODEL_PROVISIONING.md` for provenance and recovery details.

The refresh cookie is host-only: there is no cookie-domain setting. Its path is fixed to `/api/v1/auth`, it is HttpOnly, Secure in staging/production, and expiry is derived from `PICKLEBALL_AI_AUTH_REFRESH_TOKEN_DAYS`. `SameSite=lax` is valid for the HTTPS `court4.lexora.ltd` / `api.court4.lexora.ltd` same-site topology. CSRF protection uses the exact configured frontend origin; there is no duplicate CSRF-origin variable. Temporary uploads live below the configured local storage root in `_uploads`; there is no separate temporary-root setting. The only supported persistence and storage backends are PostgreSQL metadata and local filesystem bytes, respectively.

## Environment matrix

| Area | Development | Test | Staging | Production |
|---|---|---|---|---|
| Environment/debug | SET / development routes allowed | SET / test-only controls | SET / debug routes absent | SET / debug routes absent |
| Frontend and API URLs | HTTP localhost allowed | HTTP isolated origins allowed | HTTPS required | HTTPS required |
| Allowed origins | Exactly `http://localhost:3000` by default | Exact isolated test origin | Exactly frontend origin | Exactly frontend origin |
| PostgreSQL URL/pool/timeouts | SET | SET to disposable database | Required; fail closed | Required; fail closed |
| Signing secret | Development value allowed | Isolated test value | Required, non-default | Required, non-default |
| Refresh cookie | Secure may be false | Secure may be false | Secure required | Secure required |
| Registration | Explicit choice recommended | Explicit fixtures | Explicit choice required | Explicit choice required |
| Allowlist | Optional | Fixture-controlled | Required if registration is enabled | Required if registration is enabled |
| Email | Development sink allowed | Development sink unless explicit external opt-in | Real provider/key/sender required | Real provider/key/sender required |
| Storage | Writable local path | Disposable writable path | Persistent mounted path | Persistent mounted path |
| Detector model | Optional local pinned bytes | Not required for controlled fixtures | Pinned checksum-verified volume | Pinned checksum-verified volume |
| Ball tracking | Disabled by default | Disabled by default | `BALL_TRACKING_ENABLED=false` | Disabled unless separately released |
| Provenance | Local placeholders acceptable | Test identifiers | Commit and build ID required operationally | Commit and build ID required operationally |

## Current local value inventory

No secret value was printed during this audit.

| Setting group | Current status |
|---|---|
| Local `.env` | SET and ignored |
| Frontend `.env.local` | SET; now ignored |
| Deployment environment | MISSING |
| Approved HTTPS frontend/API URLs | PLACEHOLDER |
| Deployment PostgreSQL URL | MISSING |
| Deployment signing secret | MISSING |
| Explicit deployment registration/allowlist | MISSING |
| Brevo provider/API key/sender | SET locally; real delivery NOT TESTED |
| Persistent staging mount | MISSING |
| Commit/build provenance | PLACEHOLDER |

Startup validation rejects missing/default secrets, insecure cookies, development email, missing provider credentials, invalid sender, non-HTTPS frontend URLs, malformed origins, wildcard origins, registration without an allowlist, and differing production frontend/CORS origins.

Store the database password, signing secret, and Brevo key in the platform secret
manager and inject them only at runtime. Non-secret configuration belongs in the
service environment. Build `NEXT_PUBLIC_*` values into the reviewed frontend image;
never place secrets under that prefix. Keep the deployment manifest/configuration
fingerprint in restricted operational records. `.env`, `.env.local`, database dumps,
media, output, caches, `node_modules`, and build directories have ignore rules.
`web/.env.local` is ignored and contains only local public settings. Environment-
local files do not belong in a release.
