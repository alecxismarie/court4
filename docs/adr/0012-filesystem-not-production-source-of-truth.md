# ADR 0012: Application Filesystem Is Not Production Authority

Status: Accepted

## Context

Container filesystems are ephemeral and current JSON writes are not transactional or
safe across replicas.

## Decision

Production application disk is bounded scratch only. PostgreSQL owns metadata and
private storage owns bytes. Local filesystem persistence remains a development
adapter and migration source.

## Consequences

Processing downloads/uploads verified objects and cleans scratch. Existing local
analyses require explicit import; bind-mounted `data/` is not a production design.
