# Court4 production-like security checklist

Do not promote unless every required item is checked with evidence.

- [ ] Secrets originate in the deployment secret store; no `.env`, database URL, token, cookie, API key, or actionable email link appears in Git or logs.
- [ ] HTTPS is active on the frontend and API; redirect HTTP before application traffic.
- [ ] `FRONTEND_BASE_URL`, `NEXT_PUBLIC_COURT4_API_URL`, and `PICKLEBALL_AI_FRONTEND_ALLOWED_ORIGINS` are exact approved HTTPS origins with no path, wildcard, credentials, or localhost fallback.
- [ ] Refresh cookie is HttpOnly, Secure, explicitly SameSite, host-only, scoped to `/api/v1/auth`, and expires explicitly; logout clears it with matching attributes.
- [ ] A strong non-default signing secret is configured and token lifetimes are approved.
- [ ] Registration is explicitly enabled only for the private alpha; allowlist is enabled and populated. Existing login/recovery remain functional if registration is disabled.
- [ ] Mandatory verification blocks all product routes for unverified accounts.
- [ ] Bootstrap identity, legacy import, development email sink, internal calibration, Active Play debug, diagnostics, and email-inspection routes are disabled/unmounted.
- [ ] Brevo sender is exactly `Court4 <no-reply@lexora.ltd>` and real verification, resend, recovery, password-change, and session-security messages have been received and their links consumed.
- [ ] Cross-user API and private artifact access return hiding 404 responses.
- [ ] PostgreSQL backup/restore, migration head, indexes, constraints, and readiness are verified.
- [ ] Storage is persistent, writable, capacity-monitored, owner-authorized, and reconciled with PostgreSQL metadata.
- [ ] Structured logs include startup, dependency/readiness, authentication category, upload/analysis lifecycle, and email failure category without sensitive payloads. Retain staging application logs for 14 days with restricted access; redact credentials and tokens at collection.
- [ ] Current backend and frontend artifacts are built from a reviewed commit; containers are scanned and provenance IDs are set.
- [ ] Rate limits, ingress upload limit/timeout, one-processing-request operational limit, and disk hard stop are active.
- [ ] Browser smoke has no unexpected console errors, and real Brevo plus real CV workflow evidence is attached to the release record.

Brevo network reachability is deliberately not called by every `/ready` request: credentials/provider/sender are validated at startup, while delivery failures must surface in structured logs and alerts.
