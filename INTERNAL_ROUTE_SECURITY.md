# Internal route security

Production-like environments fail closed at router construction. `create_api_v1_router(settings)` mounts development-only routers only when `environment` is `development` or `test`; guessing their URLs returns 404 and they are absent from production OpenAPI. The removed `/internal/calibration` frontend page cannot be reached by a normal player.

## Route inventory

| Route(s) | Method | Authentication / authorization | Environment | Intended availability |
|---|---|---|---|---|
| `/health` | GET | Public; no data | All | Liveness probe |
| `/ready` | GET | Public; returns only DB status | All | Readiness probe |
| `/api/v1/auth/register`, `/login`, `/refresh`, `/logout`, `/verify-email`, `/forgot-password`, `/reset-password` | POST | Public credential/token boundary; origin enforcement applies to cookie mutations | All | Account lifecycle; registration separately gated |
| `/api/v1/auth/me`, `/resend-verification`, `/change-password`, `/sessions`, `/sessions/{id}`, `/sessions/revoke-all` | GET/POST/DELETE | Current authenticated account; session resources are account-scoped | All | Self-service account security |
| `/api/v1/analyses` and all analysis, frame, artifact, calibration, tracking, candidate, player and analytics descendants | GET/POST | Current owner; upload also requires verified email; other-owner identifiers are hidden as 404 | All | Player workflow |
| `/api/v1/play-history` | GET | Current owner | All | Player history |
| `/api/v1/internal/calibration-readiness` | GET | No player auth because router is not mounted outside development/test | Development/test only | Internal evidence review |
| `/api/v1/auth/development/emails` | GET | Current user can inspect only their messages; router not mounted outside development/test | Development/test only | Deterministic verification/recovery tests |
| `/api/v1/analyses/{id}/debug/active-play` | GET/POST | Owner-scoped when mounted; router not mounted outside development/test | Development/test only | Shadow evidence tooling |

There is no broad admin surface. Production tests assert all three internal route families are absent from OpenAPI and return 404. Internal reason codes remain in owner-scoped workflow responses where needed for recovery; the public landing and legal surfaces do not expose debug reports.
