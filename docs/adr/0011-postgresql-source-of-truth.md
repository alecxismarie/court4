# ADR 0011: PostgreSQL as Durable Metadata Source of Truth

Status: Accepted

## Context

Court4 needs transactions, ownership queries, uniqueness, state transitions,
idempotency, and recoverable persistence.

## Decision

Use PostgreSQL for users, uploads, analyses, runs, artifacts/storage metadata,
provenance, consent, lifecycle, and security records.

## Consequences

Schema migrations, backups, restore tests, connection management, and repository
interfaces are required. Blob bytes remain outside PostgreSQL.
