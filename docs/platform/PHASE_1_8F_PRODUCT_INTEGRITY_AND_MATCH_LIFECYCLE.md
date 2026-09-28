# Phase 1.8F — Product Integrity & Match Lifecycle

Implementation review date: 2026-09-28. Baseline: `main`, `25a9b86c5744bcf8d770f0caf268f5991e98a199`.
Changes remain uncommitted and unstaged. No push, deployment, Railway change, production/staging migration or data operation was performed.
The existing untracked `COURT4_CURRENT_STATE_AUDIT.md` was preserved.

## Scope and sequential gates

1. Private account cache isolation; durable duplicate-upload cleanup; bounded History pagination and authoritative counts; distinct dashboard retrieval errors.
2. A report-level **Manage match** link to the underlying Match Details page.
3. Separate media-only and whole-match deletion contracts, persistence, retry handling and accessible controls.
4. Honest upload preparation/transfer/finalization states and targeted player-facing terminology.

Workstreams 1 and 2 passed before lifecycle implementation. Workstream 3 passed its combined gate before Workstream 4 began. No calculation, Match IQ rule, evidence threshold, token/cookie policy, rate limit, upload limit, multipart setting, or sport feature flag was changed.

## Account cache, duplicates and History

`AccountQueryProvider` creates an identity-keyed private QueryClient beneath AuthProvider. A user change swaps the provider synchronously; clearing the previous cache on unmount also cancels its queries. Logout clears auth even when the request fails. Same-account refresh preserves the private cache; a different restored account receives a new one. The outer public cache is retained.

For direct-upload exact duplicates, the upload session persists `duplicate_cleanup_pending` and the duplicate result before deleting the newly allocated source object. The public completed result is withheld until deletion succeeds. Provider failure or a failed final database commit leaves durable intent. Upload recovery and the owner-scoped `POST /api/v1/uploads/{id}/retry-cleanup` retry it. The key is reconstructed from owner, allocation and suffix; cleanup refuses a registered video, an existing analysis allocation, or Analyze Again. Only this exact extra object is deleted. Analyze Again and different owners retain their independent sources.

History uses explicit 100-record pages, stable descending `(created_at, analysis_id)` ordering and server-side status filters. `total` is the matching owned live count; `completed_total` counts READY/LIMITED/UNSUITABLE across all live owned records, independently of page/filter. Only the selected page needs report artifact projection; metadata is still scanned across the owner's analyses. Older responses without the new count display **Unavailable**, not an invented first-page count. Dashboard retrieval failures show an error and retry instead of the empty-account welcome.

## Navigation and user actions

Reports expose **Manage match** using the route's analysis ID. Match Details remains the only lifecycle management surface. The link works from History, My Progress, direct report links and retained reports after source deletion, at mobile and desktop widths. Share-card rendering remains separate.

Two distinct controls appear in Match management:

- **Delete original video** requires its own confirmation, explains retained analysis/Match IQ/History/Progress, and warns that source-dependent reanalysis is no longer available.
- **Delete match & analysis** has a stronger destructive style and a separate permanent-deletion confirmation. Pending cleanup is visibly distinguished from success and can be retried at the match's management URL, including after reload.

Native modal dialogs have explicit Tab/Shift+Tab containment, cancellation focus restoration, accessible names and disabled actions during mutation. Escape cancels unless a request is pending. Browser checks exercise these behaviors.

## Lifecycle contract and migration

`0012_match_lifecycle.py`, revision `0012_match_lifecycle`, follows `0011_source_media`.
It adds `analyses.lifecycle_state` with a non-null server default of `live`, plus `deletion_requested_at` and `deleted_at`. A check constraint permits only `live`, `deletion_pending`, and `deleted`. Existing records remain live without rewriting analysis content.

Downgrade refuses while any non-live analysis exists. It never maps deleted records back to live or silently discards deletion intent. It can remove the columns only when every analysis remains live. Round-trip/default, downgrade-guard and schema-drift tests run against the isolated local test database. That database is upgraded to this revision; no remote database was migrated.

Whole-match deletion holds the existing exclusive, owner/analysis-scoped processing lock and locks the analysis row. Actual CV work or artifact materialization holding the shared lock produces a retryable busy response before deletion is accepted. Upload sessions still finalizing are also rejected. The application leaves run records marked processing between interactive setup steps; these idle run/stage reservations are cancelled once the exclusive lock proves no operation is running. This permits removal of failed/incomplete matches without deleting beneath an active worker. Run/stage admission and job persistence are serialized with the lifecycle row check; a stale writer cannot republish a deleted match.

The initial transaction commits `deletion_pending` before provider I/O. History and Progress list only live analyses; normal job, report, artifact and source-dependent workflow access rejects pending/deleted analyses. The separate owner-scoped lifecycle endpoint returns only ID/state so cleanup can still be managed. The UI removes the match's private cached queries and invalidates History/Progress after accepted deletion, including a failed purge.

Artifact rows remain as the durable retry manifest until exact provider and local cleanup succeeds. There is no prefix-based S3 deletion. Each remote key must match the reconstructed owner/analysis/source or versioned artifact key. Local cleanup validates containment and rejects symlinks; it covers the exact analysis and staging directories and owner-scoped processing workspaces. Provider errors are sanitized. A partial provider failure returns failure, not success; repeated deletion and missing objects are idempotent. A failed final database commit leaves the manifest and pending state for another attempt.

After purge, relational content is removed in foreign-key order: artifact registrations, selections, calibration reviews, stage executions, events and runs. Analysis payload, video identity/content metadata and upload result/client metadata are cleared. Minimal analysis/video identifiers, ownership, lifecycle/timing and idempotency/upload control records remain to prevent resurrection and support retry integrity. These are inaccessible through normal report APIs.

## Retained/deleted matrix

| Data | Delete original video | Delete match & analysis |
|---|---|---|
| Original uploaded recording | Delete | Delete |
| `tracking/tracked_players.mp4`, including registered old versions | Delete | Delete |
| Internal ball overlay and other registered playback videos | Delete | Delete |
| Local source/playback copies, partial downloads and abandoned staging videos | Delete | Delete |
| Other local match/staging files | Retain supporting evidence | Delete |
| Frames, player crops, calibration images, thumbnails | Retain minimum existing report/evidence inputs | Delete |
| Analytics JSON, measurements, timeline, movement summary, Match IQ | Retain | Delete |
| Trajectory and heatmap artifacts | Retain | Delete |
| Player selection, analysis/run/provenance metadata | Retain | Delete content; minimal lifecycle/control tombstones remain |
| Active Play and disabled ball JSON/image evidence | Retain; existing isolation remains | Delete |
| Registered share images | Retain | Delete |
| Share images already exported to a user's device | Outside server control | Outside server control |
| History entry and Progress contribution | Retain unchanged | Exclude at pending intent; recompute from remaining live evidence |
| Source-dependent reanalysis | Deny | Deny |
| Retained report/artifact access | Allow retained nonvideo evidence | Deny from pending intent onward |

Images/crops, maps and JSON remain under media-only deletion because the current factual report and player/court review use them. The report does not require the annotated tracking or ball overlay video. Media-only deletion requires completed analysis or completed Padel inspection; incomplete/failed Pickleball matches can instead use whole-match deletion. Already-deleting media is retryable; already-deleted source matches can still be wholly deleted. Earlier media-deleted records can be passed through media deletion again to purge historical retained playback videos.

## Identity, Progress and special cases

Media-only deletion preserves checksum duplicate identity and Progress evidence. Whole deletion excludes both pending and deleted analyses from checksum resolution. A fresh upload with a fresh initiation key can create a new analysis; another remaining live Analyze Again result may still legitimately resolve as a duplicate. Replaying the old upload key is rejected for a removed match. Persistence idempotency replay verifies that the referenced analysis is still live; job persistence also rejects tombstones before uploading filesystem artifacts.

Each Analyze Again allocation is independent. Shared uploaded-video references are rejected conservatively instead of deleting another analysis's source. Duplicate-only source cleanup continues safely even if its referenced report was subsequently removed. Padel remains inspection-only and never enters Pickleball interpretation; ball tracking remains disabled. Whole deletion handles existing internal artifacts without enabling either feature.

Progress is projected from the remaining live analyses using existing eligibility, deduplication, baseline, trend and comparison rules. Deletion changes the eligible input set, not the analytical formulas. Tests compare before/after totals and contributing IDs and ensure neighboring matches are unaffected.

## Terminology and transitions

Hashing/preparation emits a separate `preparing` state before network transfer; it has no invented percentage. Transfer starts at true 0%, with byte-based progress. At 100% the UI distinguishes verification/finalization from completed analysis and explains the court setup, player selection and results steps still ahead. Recovery and Analyze Again use the same stage labels.

Normal connection errors give a retry action without asking players to run a backend. Manual court setup describes marked corners; continuity-safe measurement wording describes reliably tracked stretches and retains the partial-observation limitation. Existing step-completion progress remains explicitly a count of completed steps, not an estimate of CV runtime. Qualified/provisional evidence labels and explanations remain where they communicate uncertainty. Advanced JSONL/tracking backend options remain technical controls. No analytics claim or threshold was changed.

## Validation

- Workstream 1: 65 upload/history backend tests; 34 auth tests; 39 focused frontend tests; static/diff review passed. Auth tests require a test-only port-3000 origin override because Compose's browser-test default is port 3002. No application configuration was changed for this.
- Workstream 2: 26 component/share/history tests, TypeScript and browser navigation at 390px/1280px passed.
- Workstream 3: combined lifecycle/source/history/direct-upload/auth/persistence gate **157 passed**; final abandoned-staging-copy regression **1 passed**; focused lifecycle UI **27 passed**. Provider failure, DB finalization failure, retry, owner concealment, idle/active handling, admission race, exact-key rejection, duplicate cleanup, reupload, retained report, inaccessible deleted report and migration safety are covered.
- Workstream 4: **79 focused tests passed**; final preparation-button test rerun **20 passed**; TypeScript, ESLint and diff check passed.
- Browser checks passed for account switching with successful/failed logout, 101-record pagination/filter reset, Manage match at both widths, media-only retry/retention, full-deletion retry after reload, History/Progress removal and keyboard containment/focus restoration. Browser lifecycle responses are controlled fixtures; real backend behavior is exercised by PostgreSQL/provider-fake integration tests.
- Initial final regression review (2026-09-29): blocked by nine test-typing errors. The subsequent narrow cleanup below resolves them. No workstream was reimplemented.

### Final regression evidence

The prior session's saved command-completion records were inspected before rerunning checks. The first full frontend run failed because `HTMLDialogElement` was absent in the Node test environment. After the environment guard, the full suite restarted and completed with **46 files / 259 tests passed**, exit 0. The webpack production build also completed with exit 0. Full backend pytest completed with **445 passed, 10 skipped**, exit 0, after the usage-cap event ended the agent turn. The skipped tests require the separately configured spike PostgreSQL database. The usage cap interrupted the final review/reporting; these three commands have recorded successful completion and were not assumed to pass or rerun unnecessarily.

On resumption, Ruff check passed, Ruff format check passed (**219 files**), TypeScript passed, and ESLint passed. The full Makefile mypy scope (`app scripts tests`) failed with **9 errors across 210 checked files**:

- `tests/test_match_lifecycle.py`: line 42 passes an optional checksum where a string is required; lines 149, 151 and 153 dereference optional database results without narrowing.
- The unchanged `tests/test_source_media.py`: lines 49, 58, 138, 287 and 295 report storage assignment, test-client typing, optional checksum, and two `Any` return errors.

The subsequent authorized pre-commit cleanup resolved all nine errors; full `mypy app scripts tests` now passes for 210 files. The four lifecycle changes add explicit non-null assertions for the fixture checksum and existing run/analysis records. They preserve all existing test expectations.

Before editing `tests/test_source_media.py`, its Git blob hash matched HEAD (`c9ec7763b99aa40a70c9952ac1ec4643e7008f38`), confirming all five errors were baseline issues. Each was inspected and corrected only with local typing hygiene:

- Original line 49: declare the storage variable as `LocalObjectStorage | FakeMultipartStorage`, matching the two existing fixture branches. Neither branch changes.
- Original line 58: assert the client app is `FastAPI`; `_client` constructs it through `create_app()` and already sets FastAPI dependency overrides.
- Original line 138: assert the retained checksum is non-null before duplicate lookup; the fixture writes and persists the source bytes, and the existing assertion already requires successful duplicate resolution.
- Original lines 287 and 295: assert the race test's storage is `FakeMultipartStorage` before capturing its methods. This test calls the default S3 fake fixture; its `download_file` and `stat` methods already return `ObjectMetadata`. The callback bodies and race synchronization are unchanged.

No casts, ignores, weakened assertions, product changes, or altered test scenarios were introduced. Focused regression covers both affected test files; the prior full pytest result remains applicable because this cleanup only makes existing fixture invariants explicit.

Cleanup revalidation: **29 lifecycle/source-media tests passed**, with the existing Starlette deprecation warning; full mypy passed (210 files), Ruff passed, Ruff format check passed (219 files), frontend TypeScript passed, ESLint passed, and `git diff --check` passed. Full pytest, browser E2E and production build were not repeated because no behavior or test scenario changed. The earlier full regression/build/browser results above remain the evidence for those gates. Final cleanup verdict: **READY FOR PRE-COMMIT REVIEW**. Nothing was staged, committed, pushed or deployed; Railway was not modified.

The existing browser completion records and current assertions cover successful/failed logout account isolation, the 101st History record and server filters, Manage match at 390px/1280px, media deletion failure/retry and retained reports, and whole deletion failure/reload/retry with History/Progress removal. Backend tests additionally verify actual Progress contribution recalculation. Browser lifecycle data is fixture-controlled; this is not a real-provider staging run.

The read-only Alembic history check confirms 12 linked revisions and one head, `0012_match_lifecycle`, directly after `0011_source_media`. Round-trip/default, downgrade refusal and schema-drift coverage passed in the recorded full pytest run. No database was migrated during this resumed review. `git diff --check` passed.

The final read-only security review found no new account-cache or backend owner-scope regression, cross-account/prefix deletion path, or unmanaged exact-duplicate source cleanup path. Pending/deleted analyses are excluded from History/Progress; tombstones fence stale idempotency and job writes. New source/logging paths introduce no credentials, cookies or signed URL logging; credential-pattern scanning of changed source, tests and documentation found no matches. Durable pending cleanup still requires retry after provider failure. The implementation descriptions and retention matrix above match the reviewed code; generated build artifacts remain outside the phase source review.

## Security/privacy review

Identity-keyed private caches prevent a new account from observing previous account History/Progress/Dashboard queries. Backend ownership dependencies remain unchanged. Lifecycle status/delete queries check owner before provider access. Registered provider keys are validated against reconstructed exact keys; no caller supplies a deletion key, and no S3 prefix listing/deletion is introduced. Provider-failure tests verify sanitization. New code adds no logging of tokens, cookies, presigned URLs or provider credentials. Pending/deleted records cannot contribute to subsequently projected Progress or be fetched as reports. Duplicate cleanup persists intent rather than losing an extra object on failure. Old idempotency/job writes cannot resurrect tombstoned analyses.

## Limitations and staging checks

- Purge attempts run synchronously under the deletion operation lock. Failures have durable manual retry through the match URL; no speculative background worker was added. Long provider latency should be checked in staging.
- An already-rendered/exported report or downloaded image cannot be remotely revoked. Other open tabs update through their normal refetch/navigation; there is no new cross-tab push protocol.
- History pagination bounds artifact projection, but counting/filtering still scans owned metadata. Progress recomputes with existing projection logic.
- The Windows Turbopack dev server returned 404 for existing routes during the navigation gate. Browser verification uses webpack. The production build also uses the supported webpack flag; no Next configuration/dependency change was made.
- Authorized cleanup classified all 252 untracked files before deletion: 12 intentional Phase 1.8F files, the pre-existing September audit, and 239 disposable generated files under `web/.next-e2e-phase18f/`. Only that generated directory and the ignored `web/test-results/` directory (containing `.last-run.json`) were removed after path/containment and reparse-point checks. `web/next-env.d.ts` and `web/tsconfig.json` were returned to their exact HEAD content by removing only generated-path noise. Standard ignored Next caches/type output remain available for local tooling. The September audit and every intentional phase file were preserved. No `git clean`, broad reset/restore, or staging was used.
- Before any release: independently review the migration and its downgrade guard, verify real private S3 deletion/retry and large-media removal, repeat owner-isolation/deleted-link checks against staging, check multiworker busy behavior, and confirm Progress and retained evidence on representative Pickleball and inspection-only Padel data. Verify feature flags remain unchanged. No staging checks were performed by this implementation task.
