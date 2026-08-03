# Private-alpha registration control

The restriction is a release control separate from permanent personal-account authentication.

Configuration:

- `REGISTRATION_ENABLED=true|false`
- `PRIVATE_ALPHA_ALLOWLIST_ENABLED=true|false`
- `PRIVATE_ALPHA_ALLOWED_EMAILS=email1@example.com,email2@example.com`

Development and test default to open registration for local workflows. Staging and production require an explicit `REGISTRATION_ENABLED` value. Enabling production registration also requires the allowlist toggle and at least one allowed address. Addresses are trimmed and case-folded before comparison.

Closed registration returns HTTP 403 with `REGISTRATION_CLOSED`. An address outside the active allowlist returns HTTP 403 with `PRIVATE_ALPHA_NOT_APPROVED`; the list is never returned. The frontend presents both as deliberate alpha states with an existing-user login path.

Registration controls do not affect login, verification resend, forgot/reset password, or existing sessions. No invite entity, shared code, or cross-user access was introduced.
