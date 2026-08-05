# PostgreSQL backup and restore runbook

Use PostgreSQL client tools compatible with the server. Replace angle-bracket placeholders through the secret manager; never paste credentials into shell history or logs.

## Backup

```text
pg_dump --format=custom --no-owner --no-privileges --file=<encrypted-staging-path>/court4-<UTC-timestamp>.dump <DATABASE_URL>
Get-FileHash -Algorithm SHA256 <backup-file>
Get-Item <backup-file> | Select-Object Length
```

Store the dump encrypted, access-controlled, outside Git and outside the application data volume. Keep daily backups for 14 days and weekly backups for 8 weeks for private staging, subject to the approved retention/deletion policy. Restrict restore access and record backup timestamp, PostgreSQL version, schema revision, checksum, size, and operator.

## Restore rehearsal

1. Set `ENVIRONMENT=test`, the exact expected host/user and an approved disposable
   prefix; set `ALLOW_DESTRUCTIVE_DATABASE_OPERATIONS=true` only for this command.
2. Run `assert_distinct_restore_target` before creating/restoring: source and target
   database names must differ and the target must match the approved identity.
3. Create a separate disposable database with an unmistakable validation name.
4. Restore with `pg_restore --no-owner --no-privileges --exit-on-error --dbname=<validation-url> <backup-file>`.
5. Run `alembic current`, confirm `0006_auth_onboarding`, and run `alembic check`.
6. Compare aggregate table counts and representative ownership/session/artifact rows; do not print personal data or tokens.
7. Point a disposable API process at the restored database and require `/ready` to return 200.
8. Re-check the target's live identity, terminate only its connections, then drop only
   that validation database. Clear the destructive opt-in.

For data-only recovery into an already migrated empty database, generate a table-of-contents list with `pg_restore -l`, exclude `TABLE DATA public alembic_version`, and restore the edited list with `--disable-triggers --use-list=<list>`. Prefer a normal full restore into a new database whenever possible.

Success requires a matching checksum, error-free restore, expected migration head, matching safe aggregate counts, working indexes/constraints, and a 200 readiness probe. Any missing backup, checksum mismatch, restore error, schema drift, count mismatch, or failing readiness probe blocks promotion.

## 2026-08-05 local rehearsal evidence

- Custom-format dump: `build/predeployment-backups/court4-d0-20260805.dump` (ignored by Git).
- Size: 107,125 bytes.
- SHA-256: `3DC5330D08C40B6DD013FC0FF8CD69F9F1DB37C1A4A9E139DAB80A7CB0E4B167`.
- Guarded target: `court4_validation_restore_20260805_d0`; migration head
  `0006_auth_onboarding`, representative row counts, and `/ready` passed.
- Counts before and after were unchanged: users 7, uploaded videos 3, analyses 3,
  runs 3, artifacts 663, state events 12, idempotency records 3, selections 0,
  refresh sessions 7, and verification/reset tokens 6.
- Only the disposable database and its temporary in-container dump were removed.

The earlier incident is documented in `DATABASE_TEST_ISOLATION_POLICY.md`. Current
helpers now enforce environment, opt-in, database prefix, host, user, live identity,
and distinct restore target rather than trusting a connection URL alone.
