# ADR 0002: Schema-First Platform Transition

Status: Accepted

## Context

Adding authentication before durable users, ownership, attempts, and storage
metadata would force repeated migrations and leave correctness gaps.

## Decision

Define and implement the durable platform schema and write-safety contract in Phase
1.8B before attaching authentication in Phase 1.8C.

## Consequences

Phase 1.8B includes identity-ready users but no login behavior. Ownership is not a
nullable afterthought. Auth and storage phases use stable resource IDs.
