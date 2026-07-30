# Phase 1.8B0 quarantine

This package is retained only as historical spike evidence. It is excluded from
the production package build, uses its own `spike/alembic.ini`, has prefixed
tables, and must never be imported by `app`. Production runtime and migrations
live under `app.persistence`.
