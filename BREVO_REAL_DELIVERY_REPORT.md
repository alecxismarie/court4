# Brevo real-delivery report

Status: **NOT TESTED — OPEN DEPLOYMENT BLOCKER**.

The adapter and automated tests are ready, and the local secret is present, but the
configured frontend base URL is still a placeholder, registration/allowlist values
are not fully set, and no approved inbox or inbox access was supplied. No message was
sent. A Brevo HTTP response would not be sufficient evidence, so this report does not
claim delivery, sender alignment, rendering, or link consumption.

## Required manual evidence session

Use two allowlisted addresses in real inboxes and the eventual HTTPS staging URLs.
Do not paste tokens or actionable URLs into this report.

1. Register address A and record receipt time, subject, and displayed sender
   `Court4 <no-reply@lexora.ltd>`.
2. Inspect headers and record SPF/DKIM/DMARC results without recording identifiers;
   inspect both HTML and plain-text parts.
3. Open the verification link once; confirm Dashboard handoff and onboarding modal;
   confirm a second use fails safely.
4. Register address B, request resend, verify that only the newest link succeeds and
   the older token is invalid.
5. Request password reset for A, receive and consume it, log in with the new password,
   and confirm the password-change notification.
6. Exercise the implemented session-security notification and record receipt.
7. Review redacted backend/provider logs for delivery failure category only. Confirm
   no API key, token, email body, or actionable URL was logged.

Record timestamp, browser, inbox provider, sender/alignment result, each flow's
pass/fail, and redacted screenshots or message IDs in a secure evidence location.
Only then may this gate be changed to CLOSED.
