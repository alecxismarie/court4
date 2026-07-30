# ADR 0013: Shared Match Access Deferred

Status: Accepted

## Context

Future players may share a match, but private-alpha ownership and consent behavior
must remain simple.

## Decision

Do not create SharedMatch, MatchParticipant, VideoAccessGrant, AnalysisSubject, or
ResourceShare tables in Phase 1.8. Keep opaque stable IDs and single ownership so
grants can be added later.

## Consequences

One user may not analyze another user's source during alpha. Video participants gain
no implicit access. Future sharing needs its own threat, consent, and revocation
design.
