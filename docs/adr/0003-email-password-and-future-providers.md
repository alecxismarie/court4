# ADR 0003: Email/Password with Future Providers

Status: Accepted

## Context

The permanent product needs conventional personal accounts and future Google/Apple
support. Magic-link-only or invite-token-only identity would not match that product.

## Decision

Email/password with verification, reset, and secure sessions is the first identity.
Use managed auth with a local provider-neutral identity mapping; Supabase Auth is the
preferred candidate pending a spike. Google and Apple may be linked later.

## Consequences

Provider subjects never become Court4 resource primary keys. Provider selection must
prove FastAPI JWT validation, Next.js secure session handling, deletion, revocation,
and identity linking.
