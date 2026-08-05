# Production email provider

Court4 supports `development`, `resend`, and `brevo` implementations behind its existing `EmailSender` interface. Authentication code still creates Court4-owned `EmailMessage` templates and never imports a provider adapter. Brevo architecture and manual validation are documented in `BREVO_EMAIL_PROVIDER.md`.

Required production configuration:

- `EMAIL_PROVIDER=resend`
- `RESEND_API_KEY=<secret>`
- `EMAIL_FROM_ADDRESS=<verified sender>`
- `EMAIL_FROM_NAME=Court4` (or approved equivalent)
- `FRONTEND_BASE_URL=https://<trusted frontend origin>`

For Brevo, use `EMAIL_PROVIDER=brevo` and `BREVO_API_KEY=<secret>` with the same sender and frontend settings. The intended sender is `Court4 <no-reply@lexora.ltd>` after that domain is verified by Brevo.

Production/staging startup rejects the development sink, missing/placeholder provider credentials, an invalid sender, insecure frontend links, and absent explicit registration control. The adapter supports every existing category (verification, reset, password/security notifications) through one transactional send contract. It returns `failed` for non-success responses, missing provider IDs, invalid credentials and throttling; secrets and raw tokens are not logged. Registration delivery failure rolls back the new account instead of claiming success. Forgot-password remains enumeration-safe.

Validated locally: mocked Resend acceptance/failure and mocked Brevo payload, success, credential, sender, validation, throttle, server, network, timeout, malformed-response and logging behavior. Real Resend or Brevo inbox delivery, delivered verification/reset link traversal, security-notification delivery, and provider dashboard status remain unproven. A durable outbox remains a Phase 1.8E follow-up, not part of either adapter.
