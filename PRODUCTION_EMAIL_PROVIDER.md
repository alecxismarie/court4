# Production email provider

Court4 now supports `development` and `resend` implementations behind its existing `EmailSender` interface. Authentication code still creates Court4-owned `EmailMessage` templates and never imports the provider adapter.

Required production configuration:

- `EMAIL_PROVIDER=resend`
- `RESEND_API_KEY=<secret>`
- `EMAIL_FROM_ADDRESS=<verified sender>`
- `EMAIL_FROM_NAME=Court4` (or approved equivalent)
- `FRONTEND_BASE_URL=https://<trusted frontend origin>`

Production/staging startup rejects the development sink, missing/placeholder provider credentials, an invalid sender, insecure frontend links, and absent explicit registration control. The adapter supports every existing category (verification, reset, password/security notifications) through one transactional send contract. It returns `failed` for non-success responses, missing provider IDs, invalid credentials and throttling; secrets and raw tokens are not logged. Registration delivery failure rolls back the new account instead of claiming success. Forgot-password remains enumeration-safe.

Validated locally: mocked Resend acceptance with provider ID, mocked HTTP 429 failure, production configuration rejection, and development-sink isolation. Not validated: delivery to a real Resend test domain, verification/reset link traversal from a delivered message, password-change notification delivery, or provider dashboard status. Those require an approved API key and verified sender domain and are release-blocking. A durable outbox remains a Phase 1.8E follow-up, not part of this adapter.
