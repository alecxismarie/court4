# ADR 0008: Database-Enforced Concurrency and Idempotency

Status: Accepted

## Context

Filesystem read-modify-write, double clicks, retries, and future at-least-once worker
delivery can duplicate or corrupt work.

## Decision

Commands use scoped idempotency keys, transactions, unique constraints, row versions,
formal transitions, append-only events, and one active run constraint. Worker claims
later use leases and `FOR UPDATE SKIP LOCKED`.

## Consequences

Clients can safely retry. Exactly-once delivery is not assumed. Domain failures and
stale states have explicit 409 responses.
