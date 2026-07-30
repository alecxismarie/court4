# ADR 0004: Alpha Registration Is Separate from Authentication

Status: Accepted

## Context

Private alpha limits who may register but should not create a temporary identity
architecture.

## Decision

Use an expiring approved-email allowlist and global registration toggle around the
permanent email/password registration flow.

## Consequences

Existing users can log in while registration is closed. Public beta removes the
eligibility check. No permanent Invite entity or reusable shared access code is
required.
