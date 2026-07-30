# ADR 0014: Queue-Ready Model, Worker Deferred

Status: Accepted

## Context

Current processing is synchronous, but durable attempts, retries, cancellation, and
crash recovery must not depend on that execution mechanism.

## Decision

Persist queued/processing runs, claims, leases, heartbeats, events, and idempotency
in Phase 1.8B. Continue bounded synchronous execution initially. Add a queue and
worker later without changing run identity or state authority.

## Consequences

The database remains authoritative under at-least-once queue delivery. Phase 1.8B
does not introduce queue infrastructure, and private alpha must cap synchronous
concurrency.
