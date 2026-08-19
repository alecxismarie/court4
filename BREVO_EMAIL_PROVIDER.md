# Brevo transactional email provider

## Architecture

Brevo is an adapter behind Court4's existing boundary:

```text
AuthenticationService
  -> AccountEmailService (Court4 templates and trusted links)
  -> EmailSender protocol
  -> BrevoEmailSender
  -> POST https://api.brevo.com/v3/smtp/email
```

`BrevoEmailSender` maps only provider-neutral `EmailMessage` values. Authentication code and templates do not import Brevo. Resend remains supported, and the in-memory sink remains available only in development/test.

## Local configuration

Create or update the ignored root `.env` on the development computer. Do not put provider credentials in `web/.env.local` and never commit `.env`.
`.env.example` is documentation only; Docker Compose loads the ignored `.env` and
fails when that file is absent.

```dotenv
EMAIL_PROVIDER=brevo
BREVO_API_KEY=<paste the Brevo HTTP API key locally>
EMAIL_FROM_ADDRESS=no-reply@lexora.ltd
EMAIL_FROM_NAME=Court4
FRONTEND_BASE_URL=http://localhost:3000
```

Use a Brevo API key, not an SMTP key. `no-reply@lexora.ltd` must be an approved Brevo sender/domain. Local HTTP links work only on the same development computer. Staging and production require an HTTPS `FRONTEND_BASE_URL`, a non-placeholder verified sender, the development sink disabled, and all other production security settings.

To rotate the key, create a replacement in Brevo, update only the deployment/local secret store, restart and validate Court4, then revoke the old key in Brevo. Never paste a key into source, Git history, logs, screenshots, commands, tickets, or reports.

## Provider mapping and failures

Court4 sends sender name/address, one recipient, subject, plain-text and HTML bodies, plus `X-Court4-Correlation-ID`. A successful 2xx response must contain a non-empty Brevo `messageId`; otherwise delivery fails safely.

| Provider outcome | Internal classification | Court4 result |
|---|---|---|
| 2xx plus `messageId` | sent | `sent` with provider message ID |
| 400 | validation | `failed` |
| 401 | authentication | `failed` |
| 403 | forbidden | `failed` |
| 429 | throttled | `failed`; sanitized `Retry-After` may be logged |
| 5xx | unavailable | `failed` |
| timeout | timeout | `failed` |
| network error | network | `failed` |
| malformed success body | malformed_response | `failed` |

No automatic retry is attempted, avoiding duplicate security emails. Logs contain provider/category/correlation/status metadata only—not credentials, payloads, addresses, bodies, or actionable links.

## Real-delivery checklist

Real delivery is not proven by mocked tests. With the local backend and frontend running and the key supplied through `.env`:

1. Register a new address on the private-alpha allowlist and receive the verification message.
2. Open its localhost verification link on the same computer and confirm verification.
3. Before verification, select resend, receive exactly one new message, and confirm the old link is invalidated.
4. Request forgot password and confirm the response remains generic.
5. Receive the reset message, open the localhost link, and complete reset.
6. Change the password while signed in and receive the password-changed notice.
7. Revoke another active session and receive the session-security notice.
8. Confirm no API key or raw verification/reset token appears in application logs.
9. Repeat verification and reset against the production-like HTTPS origin before release.

Record receipt, link consumption, timestamps, sender identity, and the Brevo message IDs without recording secret links or tokens.

## Known limitation

Court4 has no durable outbox, background email worker, automatic retry queue, delivery webhook, bounce handling, or complaint processing. These remain later operational work; they are not part of this adapter.
