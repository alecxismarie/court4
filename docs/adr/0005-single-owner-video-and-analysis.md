# ADR 0005: Single-Owner Video and Analysis

Status: Accepted

## Context

Videos may show several players, but appearance does not establish data ownership.

## Decision

Every UploadedVideo and Analysis has exactly one matching `owner_user_id`. The
uploader owns the source and their personal analysis. Artifacts inherit Analysis
ownership.

## Consequences

Private alpha has no co-ownership or cross-user analysis. A composite relational
constraint protects owner consistency. Future participation/sharing records can
grant access without changing the owner.
