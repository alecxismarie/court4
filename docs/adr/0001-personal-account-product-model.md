# ADR 0001: Personal Account Product Model

Status: Accepted

## Context

Court4 serves individual players. Organization/workspace tenancy would complicate
ownership and authorization without a current product need.

## Decision

One `User` is one personal account. Resources have one personal owner. There are no
organizations, teams, workspaces, or shared accounts in Phase 1.8.

## Consequences

Owner filters are simple and mandatory. Future sharing adds grants/participants
without redefining the owner. Organization billing or enterprise administration is
not pre-modeled.
