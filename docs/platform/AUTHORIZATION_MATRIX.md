# Authorization Matrix

## Global rules

- Resolve the local user from a validated session before resource lookup.
- Owner queries include both `resource_id` and `owner_user_id`.
- Return `401` for missing/invalid authentication.
- Return `404` to authenticated non-owners for private videos, analyses, runs, and
  artifacts so resource existence is hidden.
- This resource-hiding 404 rule applies before returning resource-specific state.
- Return `403` when resource existence is already known and the denial concerns
  account state or an explicit role, such as an owner whose account is unverified.
- Alpha administrators have explicit capabilities, not implicit access to all
  player content. Content access is break-glass, reasoned, time-bound, and audited.
- Workers use workload identity and a claimed `AnalysisRun`, never a player session.

Legend: A anonymous, U authenticated unverified, O verified owner, N verified
non-owner, M alpha administrator, W system worker.

| Action | Allowed actor and state | Ownership | A response | N response | Audit |
| --- | --- | --- | --- | --- | --- |
| Create account | A when registration policy permits | n/a | normal flow | n/a | eligibility outcome without raw secret |
| Verify email | A/U with valid single-use token | token user | generic invalid/expired response | n/a | success/failure |
| Log in | A with valid credentials; U gets restricted session | n/a | generic success/failure | n/a | success, throttling, session |
| Log out | U/O; idempotent if session absent | session | 204 | n/a | session revocation |
| Reset password | A with valid token | token user | generic response | n/a | request/consume/revoke-all |
| Create upload record | O active, consent current, alpha/quota allowed | new owner = actor | 401 | n/a | command and idempotency key |
| Upload video bytes | O active or scoped upload credential | upload owner | 401 | 404 | start/complete/failure |
| Start analysis | O active | video owner and analysis owner | 401 | 404 | provenance/request fingerprint |
| List analyses | O active | implicit owner filter | 401 | only own list | read audit sampled, not every poll |
| Read analysis | O active | analysis owner | 401 | 404 | sensitive access policy |
| Retry analysis | O active | analysis owner | 401 | 404 | new run and reason |
| Cancel analysis | O active; W honors cancellation | analysis owner | 401 | 404 | transition |
| Delete analysis | O active/deletion-pending account flow | analysis owner | 401 | 404 | deletion request and completion |
| Read Analysis History | O active | owner-scoped projection | 401 | only own history | sampled |
| Read Play History | O active | owner-scoped qualified projection | 401 | only own history | sampled |
| Download artifact | O active; M break-glass; W claimed run | indirect analysis owner | 401 | 404 | downloads for sensitive categories |
| Read source metadata | O active | video owner | 401 | 404 | sampled |
| Delete source video | O active if dependent-analysis policy satisfied | video owner | 401 | 404 | dependency decision and purge |
| Submit feedback | O active; U only verification feedback if offered | optional referenced analysis owner | 401 | 404 if foreign reference | submission |
| Internal endpoints | M with named capability; W only machine endpoint needed | n/a | 401/404 | 404 | every access |
| Debug endpoints | no player access in production; M/W with capability | claimed/approved analysis | 404 | 404 | every access and reason |
| Change settings/profile | O active | user self | 401 | n/a | security-relevant changes |
| Delete account | O active after recent re-authentication | user self | 401 | n/a | request, cancel, each purge stage |
| Admin user management | M with `users:manage`; no content by default | explicit target | 401 | 403 | every action |

## Account-state effects

| State | Login | Existing reads | Upload/analyze | Download | Feedback | Billing later |
| --- | --- | --- | --- | --- | --- | --- |
| `pending_verification` | Restricted | No player data | No | No | Verification support only | None |
| `active` | Yes | Yes, owner-scoped | Yes, policy/quota permitting | Yes | Yes | Normal |
| `disabled` | No new session | No, except approved recovery/export | No | No | Support channel | Stop renewal decision required |
| `suspended` | No | No | No | No | Support channel | Product decision |
| `deletion_pending` | Restricted re-auth | Export/cancel only | No | Export only if offered | Support | Cancel/terminate decision required |
| `deleted` | No | No | No | No | No | Detached/tombstoned |

## Administrative capability set

Minimum capabilities are `users:read`, `users:manage`, `registration:manage`,
`operations:read`, `runs:repair`, and `content:break_glass`. An administrator role
does not automatically include `content:break_glass`. Break-glass access records
case/reason, target, approver if required, start, expiry, and actions.

## Ownership query patterns

Safe:

```sql
select * from analyses where id = :analysis_id and owner_user_id = :current_user_id;
```

Unsafe:

```sql
select * from analyses where id = :analysis_id;
-- followed by a later ownership check
```

Artifact authorization joins artifact → analysis and filters the analysis owner in
the query. Signed URLs are minted only after that check and expire quickly. Worker
access joins the artifact/run to the worker's active claim.

## Cross-user sharing

There is no sharing during private alpha. Future `ResourceShare`,
`VideoAccessGrant`, `MatchParticipant`, `SharedMatch`, or `AnalysisSubject` records
can add access without changing `owner_user_id`. Participation in footage never
implies ownership.
