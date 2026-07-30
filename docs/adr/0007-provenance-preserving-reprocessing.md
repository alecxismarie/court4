# ADR 0007: Provenance-Preserving Reprocessing

Status: Accepted

## Context

Overwriting analysis output would make historical evidence and policy claims
unverifiable.

## Decision

A logical Analysis owns immutable AnalysisRuns. Retry/reprocess creates a new run
with frozen source, model, policy, configuration, software, and artifact checksums.
Successful promotion changes `current_run_id`; old runs remain.

## Consequences

Failed reprocessing does not destroy the last completed result. Storage usage grows
and needs retention. Histories can explain and compare source versions.
