# Security and Hardening Plan

Classification:

- **B** blocks Phase 1.8B correctness;
- **A** blocks private alpha;
- **P** blocks public beta;
- **L** later hardening.

| Work item | Gate | Required action |
| --- | --- | --- |
| Ownership fields/invariants | B | Durable owner on videos/analyses; composite ownership constraint |
| Transactional writes/idempotency | B | PostgreSQL repository, run/event model, CAS/constraints |
| Provenance and checksums | B | Freeze run bundle; source/model/artifact hashes |
| Dependency advisories | A | Upgrade supported Next.js/PostCSS and Playwright; run npm audit in CI |
| Python reproducibility | A | Lock production dependencies; scan image/SBOM |
| Authentication/session security | A | Verified email/password, secure cookies/tokens, revocation |
| Authorization/private artifacts | A | Owner-filtered queries, hiding 404, short signed URLs |
| Internal/debug routes | A | Separate admin/internal router/network; disabled from player surface |
| Container root/dev dependencies | A | Multi-stage image, production extras only, non-root, read-only root where practical |
| Health/readiness | A | Liveness plus protected dependency readiness |
| CORS/HTTPS/secrets | A | Exact production origins, TLS only, secret manager, no local defaults |
| Consent before upload | A | Versioned required acceptance and upload representation |
| Upload limits/file validation | A | Server/storage size limits, signature/container probing, quarantine failures |
| Rate limits/quotas | A | Auth and IP limits for auth/upload/analyze/download; bounded concurrency |
| Retention/deletion | A | Owner delete, account delete, failed upload cleanup, reconciliation |
| Backups/restore | A | Encrypted backups, access limits, successful restore test |
| Logging redaction/context | A | request/user/run IDs; redact tokens, emails, paths, signed URLs |
| CSRF | A if cookies | Same-origin BFF/origin validation and CSRF token for state changes |
| Password security | A if self-managed | Argon2id, breached-password policy, reset revocation; prefer managed auth |
| Account enumeration | A | Uniform register/login/reset responses and throttling |
| Monitoring/alerts | A | availability, 5xx, stuck runs, storage mismatch, auth abuse |
| CSP/security headers | P | CSP, HSTS, frame-ancestors, referrer and permissions policies |
| Malware scanning | P/risk-based | Evaluate upload scanning; video parser sandbox and quarantine |
| Admin break-glass approvals | P | Explicit capability, reason, expiry, audit/alert |
| Penetration test | P | Auth, IDOR, signed URL, upload/parser, CSRF, admin surfaces |
| Key rotation drills | P | Auth JWKS, signing, DB/storage/email secrets |
| Advanced anomaly detection | L | Credential stuffing and unusual download/compute behavior |

## Current findings

### Dependencies

The July 2026 audit of installed frontend packages reported four high-severity npm
findings. Production-relevant findings affect Next.js 14.2.35 and its bundled
PostCSS; Playwright findings affect development tooling. Do not deploy that lockfile
unchanged. Upgrade to a supported patched Next.js line, update matching React and
ESLint configuration deliberately, then run unit, E2E, build, and audit checks.

The backend has version ranges but no lock. The documented Dockerfile upgrades pip
and installs dev/detector extras; produce a locked, scanned production dependency
set and separate heavy detector build if necessary.

### Upload and parser boundary

Current extension and MIME checks are useful but not content proof. Continue
streaming size enforcement, inspect container signatures/codecs in a sandboxed
non-root process, cap duration/resolution/frames and decompression work, use scratch
quotas/timeouts, and quarantine invalid inputs. Client limits are advisory only.

### Sessions and CSRF

Do not store bearer or refresh tokens in localStorage. Cookies are
`HttpOnly; Secure; SameSite=Lax` (or stricter when flows permit), scoped narrowly,
rotated, and paired with CSRF defense for state changes. Validate request `Origin`
and provider token issuer/audience/expiry. Password reset revokes sessions.

### Artifact access and signed URLs

Authorize by owner before minting a signed URL. TTL should be minutes, disposition
and response content type constrained, and keys private. Avoid logging the signed
query string. Non-owner receives 404.

### Logging

Add `request_id`, local `user_id`, `analysis_id`, `run_id`, safe command name,
idempotency hash prefix, build ID, and worker claim ID. Do not log passwords, tokens,
cookies, authorization headers, raw email, source filenames if sensitive, signed
URLs, raw consent evidence, video content, or unredacted provider errors.

## CI release gates

- locked dependency install and vulnerability policy;
- secrets scan and container/SBOM scan;
- backend/frontend unit, type, lint, build, and browser tests;
- migration upgrade/downgrade/forward-compatibility test;
- authorization tests for every actor/resource combination;
- idempotency/concurrency tests with parallel requests;
- storage traversal/ownership/signed-URL tests;
- backup restore and deletion reconciliation evidence for alpha release.

Risk acceptance requires owner, rationale, scope, compensating controls, and expiry;
it is not a permanent “known issue” list.
