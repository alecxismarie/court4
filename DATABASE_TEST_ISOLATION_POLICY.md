# Database test-isolation policy

Status: **CLOSED** for the Phase 1.8D0 guard. This policy applies to tests, E2E,
migration rehearsals, restore validation, fixture cleanup, schema downgrade, and
any other destructive database helper.

## Incident and permanent rule

A validation container inherited `PICKLEBALL_AI_DATABASE_URL` from the local
environment. Its cleanup fixture trusted `ENVIRONMENT=test` and issued `TRUNCATE`
against the primary local database. Environment labels alone are not database
identity. The permanent rule is: every destructive operation must fail closed and
re-check the live connection identity immediately before it changes data.

## Required identity

An approved operation requires all of the following:

- `PICKLEBALL_AI_ENVIRONMENT=test`;
- `PICKLEBALL_AI_ALLOW_DESTRUCTIVE_DATABASE_OPERATIONS=true`;
- an exact expected host and user;
- a database name equal to the configured prefix or beginning with `<prefix>_`;
- for restore validation, a target different from the source database.

The defaults are `court4_test`, `127.0.0.1`, and `court4_test`. E2E adds a separate
browser-runner handshake: `COURT4_E2E_API_URL`, `COURT4_E2E_DATABASE_NAME`, and the
exact marker `COURT4_E2E_ISOLATION_CONFIRMATION=court4-e2e-isolated`. The runner
checks the API's test-only database-identity endpoint before Playwright starts.
That endpoint is absent from production routing and excluded from OpenAPI.

`tests/conftest.py` deliberately ignores the root primary URL. Only
`COURT4_TEST_DATABASE_URL` can override its safe test default. The migration wrapper
is `python scripts/safe_migration.py ...`; it applies the same guard before Alembic.
Errors report the failed identity condition and never echo credentials.

## Operator checklist

1. Name a disposable database with the approved prefix.
2. Set its expected host, user, and name/prefix independently of the connection URL.
3. Set the destructive opt-in only for that command or isolated container.
4. Confirm the live identity immediately before truncate, downgrade, drop, or reset.
5. Clear the opt-in when the operation ends.

The test matrix covers approved isolation and refusal of development, staging,
production, missing environment, unexpected database, missing opt-in, inherited
primary URL, same-database restore, and credential-safe errors.
