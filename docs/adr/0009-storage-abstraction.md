# ADR 0009: Provider-Neutral Private Storage

Status: Accepted

## Context

Large private video bytes should not be durable application-container files, and a
single storage vendor has not been selected.

## Decision

Domain records reference StorageObject IDs through a provider-neutral interface.
Production uses private object storage; local development uses a filesystem adapter.
Direct resumable upload and short authorized downloads are preferred.

## Consequences

Provider keys do not leak into API contracts. DB/object reconciliation and
asynchronous cleanup are required. Object metadata and checksums are durable.
