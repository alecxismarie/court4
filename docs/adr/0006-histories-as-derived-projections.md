# ADR 0006: Histories as Derived Projections

Status: Accepted

## Context

Current history semantics derive from analysis evidence and versioned contribution,
comparability, trend, grouping, and interpretation policies.

## Decision

Analysis History and Play History remain owner-scoped, rebuildable projections over
durable analyses/runs. They are not editable source tables.

## Consequences

One source of truth is preserved. Materialized caches may be added only with source
fingerprints, projection versions, deterministic rebuild, and invalidation.
