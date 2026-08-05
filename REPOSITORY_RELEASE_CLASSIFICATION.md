# Phase 1.8D0 repository release classification

Snapshot: 2026-08-05, branch `main`, HEAD `1a85dca` (three local commits beyond the
recorded remote baseline). No files were staged. Explicit exceptions below override
directory patterns.

| Category | Changed/untracked paths |
|---|---|
| INTENDED RELEASE SOURCE | `.env.example`, `.gitignore`; all changed/untracked Python beneath `app/`, `scripts/`, `spike/`, and `tests/`; `web/app/api/share-artifact/**`, `web/app/layout.tsx`, `web/app/login/page.tsx`, `web/app/register/page.tsx`, `web/app/upload-match/page.tsx`, `web/components/app-shell*`, `web/components/auth-*`, `web/components/dashboard-workspace.tsx`, `web/components/email-verification*`, `web/components/first-time-profile-modal*`, `web/e2e/**`, `web/lib/api/**`, `web/lib/auth-*`, `web/lib/env*`, `web/lib/profile-onboarding.ts`, `web/lib/use-player-profile*`, `web/next-env.d.ts`, `web/package*.json`, `web/playwright.config.ts`, `web/scripts/run-e2e.mjs` |
| GENERATED OUTPUT | untracked generated `web/AGENTS.md`, `web/CLAUDE.md`; ignored `.next/`, `build/`, caches, coverage/results, `__pycache__/`, `*.egg-info` |
| LOCAL SECRET OR CONFIGURATION | root `.env` is ignored; `web/.env.local` contains only public localhost configuration but is historically tracked and must be removed from the index before release; never stage its contents again |
| USER DATA OR MEDIA | ignored `data/input/**`, `data/output/**`, models/uploads/analysis artifacts; never stage |
| TEST ARTIFACT | ignored Playwright reports/results, `build/d0-*`, dump and reconciliation output |
| DOCUMENTATION | every changed/untracked root `*.md` other than generated web instructions, plus `docs/**/*.md`; intended documentation requiring review |
| UNRELATED DEVELOPER WORK | `web/scripts/capture-landing.mjs` (local visual-capture utility; release need unproven) |
| UNKNOWN | `web/app/landing.css`, `web/components/landing/**`, `web/lib/landing-content.ts`, modified `web/public/brand/court4-logo*.png`, untracked `web/public/auth/**`, and untracked `web/public/landing/{apparel-and-gear-hd.png,apparel-and-gear.jpg,apparel-navy.png,apparel-store-navy.png,apparelandgear.png,court4-insights-pickleball.png,court4-insights-rally-v2.png,court4-insights-rally-v3.png,court4-insights-rally.png}` |

The Python group includes the untracked Brevo adapter, migration file (revision ID
`0006_auth_onboarding`), database guard, reconciliation, cleanup/migration scripts,
tests, and D0 storage changes. The web group includes verification handoff,
mandatory verification, auth redirect, E2E isolation, and real-analysis coverage.
Classification is not equivalent to owner approval.

`git diff --check` passes. Migration base-to-head, downgrade/re-upgrade, and
`alembic check` pass. Ignore rules cover `.env`, local frontend configuration,
database dumps, media/output, logs/caches, virtual environments, `node_modules`, and
build output. Ignore rules do not retroactively untrack files: `web/.env.local`
remains in HEAD. It contains no secret but is a release-hygiene blocker. No final
staged diff exists because the UNKNOWN set makes it ambiguous.

After owner review, use path-scoped commands only:

```text
git status --short
git diff --check
git rm --cached -- web/.env.local
git add -- <each explicitly reviewed source and documentation path>
git diff --cached --check
git diff --cached --stat
git diff --cached
git commit -m "chore: close phase 1.8d0 deployment blockers"
```

Do not use `git add .`. Re-run all gates from the resulting commit before an image
build.
