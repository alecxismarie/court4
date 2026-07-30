# ADR 0010: Versioned Consent Before Upload

Status: Accepted

## Context

Court4 cannot assume permission to use recordings for debugging, calibration,
evaluation, product improvement, or model training.

## Decision

Store immutable agreement versions and timestamped acceptances. Required platform
terms, optional data-use purposes, and per-upload permission representation are
separate. Validate required acceptance before reserving upload bytes.

## Consequences

Optional withdrawal is auditable and can trigger dataset cleanup. Product/legal must
approve language, purposes, retention, participant/minor rules, and consequences.
