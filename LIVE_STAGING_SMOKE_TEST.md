# Live private-staging smoke test

Run only after the environment is private, TLS is valid, migrations and restore rehearsal pass, and an approved inbox plus sample match video are available. Record UTC time, commit/build ID, browser/device, tester, analysis ID, and redacted evidence. Never record tokens or secret URLs.

1. Confirm `/health` returns 200 and `/ready` reports database and storage ready.
2. Open the HTTPS landing page on desktop and mobile; check Privacy and Terms and require zero unexpected console errors.
3. Register an approved, unique test email. Confirm a non-allowlisted address receives a typed rejection that does not disclose the allowlist.
4. Receive the real verification email from `Court4 <no-reply@lexora.ltd>`; inspect subject, HTML and text alternatives, then consume the HTTPS link.
5. Confirm authenticated Dashboard handoff, the “What should we call you?” modal, saved onboarding name, and mandatory activation behavior before verification.
6. Resend verification with a second fresh account and consume only the newest usable link according to policy.
7. Log out, log in, refresh/restore the intended session, inspect Settings/active sessions, revoke a session, and confirm cookie behavior.
8. Request password recovery, receive and consume the real reset link, confirm prior sessions are handled as designed, and receive password-change/session-security notifications where implemented.
9. Upload an approved real video no larger than 512 MiB. Confirm an unverified/unauthenticated user cannot reserve bytes.
10. Re-upload the exact bytes, observe duplicate detection, choose Analyze Again, and confirm the owner-scoped new workflow.
11. Run court detection, find players, select the player, complete analytics, and inspect Movement Measurements plus Match IQ or its honest suppression reason.
12. Inspect Dashboard, Analysis History, Play History, analysis detail, artifacts/share endpoints, and Settings.
13. With a second verified account, request the first account's analysis, history, and artifacts; require hiding 404 responses.
14. Log out and confirm private routes no longer render authenticated data.
15. Review structured logs for lifecycle/error visibility and absence of passwords, cookies, API keys, tokens, email bodies, database URLs, and actionable links.
16. Check PostgreSQL connections, filesystem growth, `_uploads`, free bytes, and alert thresholds before signing the result.

Any missing real email, broken/incorrect link, debug route, cross-user disclosure, failed readiness dependency, storage persistence failure, console regression, or incomplete real analysis keeps the release gate closed.
