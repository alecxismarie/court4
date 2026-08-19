# Private-alpha release gate

Status: **NOT READY** as of 2026-08-05.

| Gate | State | Evidence / required action |
|---|---|---|
| Database isolation guard | CLOSED | Environment, opt-in, expected host/user/prefix, live identity, E2E handshake |
| Backup/restore | CLOSED | Checksummed dump, distinct guarded restore, revision/counts/readiness pass |
| Real browser-to-CV flow | CLOSED | Real 61.2-second sample completed; persistence/histories/cross-user denial pass |
| Storage capacity guard | CLOSED | 10 GiB warning, 5 GiB hard stop, reservation, typed 429/507 |
| Storage cleanup command | ACCEPTED FOR STAGING | Dry-run and quarantine-only; completed analyses never auto-deleted |
| Storage reconciliation | OPEN | Registered rows match; 9,131 unregistered files need owner disposition |
| Real Brevo delivery/link consumption | NOT TESTED | Approved inbox/HTTPS URLs and manual evidence session required |
| Local auth/email consistency | CLOSED | Canonical localhost origin, runtime `.env`, refresh cleanup, resend recovery, delivery-mode copy and isolated tests |
| Repository release checkpoint | OPEN | Mixed intended/unknown work remains; historically tracked `web/.env.local` must be untracked |
| Current-source backend image | OPEN | 20 GiB reserve not met; existing image stale/root/no healthcheck |
| Backend engineering gates | CLOSED | 292 tests, Ruff, format, Mypy, migration cycle/check |
| Frontend engineering gates | CLOSED | 184 tests, lint, typecheck, 22-page production build, production audit 0 |
| Standard browser suite | CLOSED | 29 pass; real scenario is separately gated and evidenced |
| Staging infrastructure/secrets/HTTPS | OPEN | Specification/template exist; nothing provisioned and provenance placeholders remain |
| Full object-storage lifecycle | DEFERRED | Explicitly outside Phase 1.8D0 |
| Legal-policy approval | DEFERRED | Product/legal owner approval remains outside engineering validation |

Promotion is prohibited until Brevo evidence, repository review/checkpoint, storage
disposition, adequate host/build space, a source-current hardened image, and actual
staging infrastructure/secrets/HTTPS/monitoring are all closed.
