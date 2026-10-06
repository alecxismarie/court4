# Current Court4 Task

## Phase 1.3B — PRECOMMIT BLOCKER FIXES COMPLETE (2026-10-06)
- Final state: all three precommit blockers are resolved and the uncommitted tree is ready for precommit re-review. No staging, commit, push or deployment was performed.
- Blocker 1 resolved: legacy v1/v2/v3 candidate spans retain their historical version and cannot receive v4 continuity assurances or enter current mutation/analytics paths; explicit regeneration from original observations is required.
- Blocker 2 resolved: candidate/selection evidence changes retire dependent analytics, Match IQ, Active Play, report, History and Progress authority through the concurrency-protected persistence path while preserving source media.
- Blocker 3 resolved: raw selection resolves an eligible current v4 candidate before any write, then synchronizes raw track, candidate/source IDs and readiness; invalid requests preserve the prior selection and return the established HTTP 400 response.
- Reconstruction complete: inspected the existing tree and preserved the prior implementation, then resumed validation from the recoverable interrupted JUnit result. Production behavior changed only for the previously identified HTTP 400 compatibility defect; subsequent fixes were fixture/test-isolation corrections.
- Deferred non-blockers: legacy calculate_distance_metrics cleanup, dense fragment-association benchmark, and broader boundary-test expansion.
- Milestone: v1/v2/v3 retain their historical payload/version on load, have no current readiness in candidate API responses, cannot be selected/merged/restored/unmerged, and require explicit full regeneration from original observations. Legacy-derived analytics/Match IQ/Active Play reads and History contribution are gated. Regeneration recomputes every candidate, preserves compatible rejection/manual-merge decisions, clears legacy selection, and requires fresh selection; no relabeling.
- Milestone: workflow synchronizes tracking, candidate membership and readiness before analytics; raw selection resolves an eligible current candidate first or rejects without changing the previous selection. Selected evidence signatures bind v4 candidate evidence, selected observations and readiness (excluding assessment timestamps). Changed/invalidated evidence clears completion, retires analytics/Match IQ/Active Play artifact registrations through the existing row-version-checked persistence transaction, and keeps source media. Unchanged selected evidence preserves completed results.
- Validation: original continuity/candidate/tracking/Active Play suite 63 passed; first new blocker regression run 10 passed; Match Details UI 33 passed including explicit legacy v1/v2/v3 and v4 assertions. Added persisted invalidation/reselection, stale-save, raw eligible/missing/rejected candidate, large-gap legacy and mutation regressions.
- Expanded focused run: 177 passed, 6 failed. Individually: `test_full_controlled_api_workflow` exposed this fix's HTTP 409-versus-400 regression for an invalid raw selection (production response corrected to preserve 400); the four `test_s3_candidate_get_is_narrow_owner_scoped_and_integrity_checked` size/checksum x retained/deleted cases and `test_s3_tracking_uses_admitted_workspace_and_retries_disk_full` were stale pre-existing fixtures missing required calibration verification. Updated only those fixtures to create/confirm calibration through production APIs; the source-deleted cases now set the actual persisted video state. No production calibration gate weakened. The corrected focused rerun passed 79 tests.
- Frontend/static milestone: TypeScript and full ESLint passed. Candidate-review success now clears cached analytics and invalidates History/Progress queries, with regression assertions. Backend tests also assert S3 completed measurements are retired after a selected merge.
- Latest validation: corrected focused rerun 79 passed (full direct-upload module included); strengthened lineage regression rerun 10 passed, now proving a previously included Progress contribution is removed, qualified observation seconds return to zero, and fresh selection can produce results again. Full frontend Vitest 310 passed in 50 files; final TypeScript and ESLint passed.
- Interrupted complete-suite result was recovered from `data/output/phase13b-blockers/broad.xml`: 49 failures. Two analytics-workspace cases were stale fixtures missing current v4 candidate evidence. The other 47 were environment/order failures: Compose supplied port-3002 origin settings where tests require the canonical port-3000 topology, and Alembic logging configuration disabled existing application loggers before observability assertions. A targeted run of all affected areas with the canonical origin environment passed 153 tests after the analytics fixture used the real calibration and v4 candidate-generation flow.
- The first corrected complete rerun had 535 passed, 10 skipped and four failures. Each failure was an order/global-state logging-capture issue: the direct-upload success, checksum-mismatch and size-mismatch tests, plus the upload-observability exception-detail test. The test fixtures now explicitly restore their application logger after Alembic `fileConfig`, matching the established refresh-observability isolation pattern; an ordering reproduction passed 7 tests. No production invariant was changed.
- Final complete backend suite, with all modules included: 539 passed, 10 skipped, one Starlette/httpx deprecation warning in 751.85 seconds. Final changed-backend mypy passed in 23 source files; Ruff passed; formatting check reported 160 files already formatted; `git diff --check` passed. The earlier final TypeScript and ESLint results remain current because no frontend file changed afterward.
- Final scope checks: Court Vision code is unchanged and the reviewed-real manifest remains at 0 frames; Padel was not expanded; `.env.example` retains `BALL_TRACKING_ENABLED=false`; no real-video artifact was retained.

## Previous Phase 1.3B implementation and validation (2026-10-05)
- Task: Real-Video Player Track Continuity & Candidate Review for existing Pickleball tracking, candidate review and downstream evidence integrity. No model, detector threshold, ByteTrack setting, biometric identity, deployment, staging, commit or push is included.
- Defects demonstrated before fixes: same-ID first-to-last spans inflated observed duration across gaps; analytics paired samples after removing invalid observations; interpolation/exclusion flags did not consistently break evidence; ambiguous fragments could be greedily joined; candidate endpoints could borrow earlier court evidence; raw selection retained stale candidate lineage; and trajectories drew lines across unsupported intervals.
- Implemented one shared continuity contract: an observed court position is in court, not excluded and not interpolated; an observed interval also requires the same raw track ID, increasing frame/time and a gap no greater than one second. This is short-term continuity evidence only, not personal identity. Callers retain the original stream order so an invalid sample breaks the segment.
- Candidate schema is version 4. Candidate/raw durations, distances, previews, in-court ratios and readiness now use supported observations and intervals. Association abstains when competing predecessor/successor evidence conflicts, simultaneous overlap is incompatible, and endpoint evidence must exist at the endpoint time. Rebuilds clear selections that no longer survive; raw selection resets candidate/source lineage before remapping.
- Movement, zone, summary and Active Play calculations use the same evidence boundary. Timeline positions identify segment starts so the UI renders points without drawing unsupported bridge lines. The candidate UI exposes lazy authenticated timestamped evidence views and states that samples do not confirm identity and missing intervals are excluded.
- Focused validation: the six new defect regressions failed before implementation. Final candidate/movement/tracking/Active Play run: 63 passed, 1 warning. Broader candidate/analytics/quality/Match IQ/calibration/history run: 107 passed, 1 warning. Match details UI: 30 passed. Frontend typecheck and scoped ESLint passed. Scoped Ruff lint/format, scoped mypy and `git diff --check` passed.
- Broad backend validation excluding unchanged `tests/test_direct_uploads.py`: 476 passed, 10 skipped, 3 failed and 1 errored. The two settings failures were missing Dockerfile/web mounts and passed together when mounted (2 passed). The logging failure and database cleanup timeout both passed in fresh isolated runs (1 passed each), classifying them as suite-environment/order interference. The excluded direct-upload fixtures predate the verified-calibration gate and receive the expected 409 until they create and verify calibration; the Phase 1.3B S3 fixture uses the real verification API and passes. No product gate was weakened.
- User-authorized transient inspection covered the three existing 171.108s/61.2s/14.4s recordings. Historical outputs contain 664/161/2 raw IDs at recorded rates of 16.47/15.56/8.16 FPS; these are tracker IDs, not people. Twelve diagnostic views per source exposed background/spectator court-mask leakage and ID changes in the longer clips. Fresh five-second YOLO/ByteTrack smoke windows executed without empty frames and produced 23/22/2 raw IDs at approximately 11.0/16.78/13.25 FPS. These diagnostics establish execution and failure modes only, not identity or accuracy.
- All transient diagnostic images/helpers were removed. No real footage, extracted image, dataset fixture or benchmark label was retained. The reviewed-real manifest remains empty and Court Vision benchmark/pilot artifacts are unchanged. Padel remains gated, `BALL_TRACKING_ENABLED=false`, and no Railway/configuration variable changed.
- Remaining evidence limits: the current detector/court mask admits background people, ByteTrack IDs fragment in longer recordings, and no reviewed real identity ground truth exists. The implementation therefore preserves gaps and ambiguity instead of claiming recovered identity, recall or measurement accuracy. Full-video processing remains slower than real time on the inspected hardware.

## Previous status
COMPLETE — Candidate-Source Inventory & Provenance Assessment (2026-10-02)

## Current task
Premium Pickleball Court Vision — inventory eligible real Pickleball source material, establish only supported provenance and diversity facts, and assess gaps against the committed 120-frame pilot protocol. Inventory only: no final frame selection/extraction, labeling, detector evaluation, training or production integration.

## Candidate-source inventory progress
- Started from clean `main` at pilot-preparation commit `fbaf41c3496ca8e290ba229e5f5f506fb0c467a9`; read the permanent context, design audit, Phase 1 benchmark contract, pilot protocol and empty ledger.
- Phase 1 Offline Benchmark Foundation remains COMPLETE. The 120-frame Dataset Pilot Preparation remains COMPLETE. Candidate-Source Inventory & Provenance Assessment is the CURRENT TASK.
- The reviewed-real manifest remains at 0 frames and the pilot review ledger remains at 0 actual data rows. The 120-frame collection/review is NOT STARTED.
- Completed scope: traced locally accessible candidate recordings and the previously observed sampled images through repository metadata and artifacts, distinguished established/derived/human-assessed/unknown facts, and reported feasibility gaps without selecting pilot frames.
- Milestone 1: hashed 179 local sampled-frame JPEG files across 144 analysis directories and confirmed 24 unique image contents. Ten unique real images (29 copies) trace to three distinct local source-video hashes; the other 14 unique images (150 copies) are blank/tiny or synthetic validation fixtures and are ineligible.
- Milestone 2: added a three-row source inventory and assessment. All three real sources are `questionable`: source bytes and analysis relationships are established, but dataset-use/retention authority and physical court/venue/camera/shot provenance are not. No source is currently pilot-eligible.
- Current feasibility: three conservative source-scoped recording/camera groups, zero provenance-established physical courts, venues or physical camera identities, and zero eligible sources cannot satisfy the protocol's 20-group, approximately eight-court, approximately five-venue or 120-frame requirements. Additional provenance-cleared footage is required.
- Final validation: inventory sums trace to 3 distinct source hashes, 3 source-scoped groups, 10 unique real sampled hashes, 29 real sampled-file copies and 19 redundant copies. The reviewed-real manifest remains at 0 frames; the pilot ledger remains at 0 data rows; Phase 1 and pilot-preparation files, production/benchmark code, configuration and deployment files are unchanged. `git diff --check` passed. No frames were selected/extracted or labeled, no detector evaluation ran, no model was trained and nothing was deployed.

## Dataset pilot preparation progress
- Started from clean `main` at Phase 1 commit `e9f9d30c6bde69ce0f8c80ceecd040dd51875824`; reviewed the permanent context, Phase 1 contract, design audit, annotation template/manifest and relevant implementation history.
- Phase 1 Offline Benchmark Foundation remains complete and unchanged. The reviewed-real manifest still contains zero frames. Actual 120-frame collection/review is NOT STARTED.
- Current work: lock the exact sampling, orientation, independent review/adjudication, provenance/grouping, diversity, completion-gate and future baseline-evaluation protocol without changing the validated schema or evaluator.
- Milestone 1: added `calibration/court_vision/PILOT_PROTOCOL.md` with an exact 50/40/20/10 sampling structure, group contribution caps, controlled diversity tags, decoded-image orientation convention and schematic, blind annotation/review/adjudication procedure, provenance rules, completion gates, candidate-image handling and future baseline formulas. Added a header-only review ledger template for backward-compatible disagreement/derivation records; it contains no candidate data.
- Milestone 2: completed a standalone safety review, resolved the prior left/right ambiguity, kept all pilot records in `development` until any future split is authorized, and documented how pre-existing known failures may be declared without detector-driven sample mining. The schema, evaluator, frame template and empty manifest remain byte-unchanged from Phase 1.
- Final validation: reviewed-real manifest = 0 frames; ledger template = 30 unique columns and 0 data rows; documentation and untracked-file whitespace checks passed; git status contains only this preparation documentation/handoff scope. No benchmark code was touched, so Python tests/static checks were not rerun.
- Preparation is complete. Actual 120-frame collection/review remains NOT STARTED and requires separate authorization.

## Phase 1 Offline Benchmark Foundation — COMPLETE

Implement the offline benchmark foundation authorized by the user: annotation validation, unchanged detector replay, independent geometric metrics, outcomes, grouped machine/human reports and focused tests. No production changes or model training.

## Phase 1 progress
- Continuation resumed on 2026-10-02 from the interrupted working tree. Revalidated the existing foundation as authoritative before making the final reporting clarification; permanent context commit `93783a54cbf558e7fd2469fba96150e82d77e049` remains untouched.
- Re-read instructions, handoff and design audit; inspected git status/diff. Existing handoff/audit changes belong to the prior design task and will be preserved.
- Starting implementation under scripts/, calibration/court_vision/ and focused tests only. Dataset labels will not be fabricated from detector outputs or synthetic tests.
- Milestone 1: added offline 12-keypoint/eight-line schema, visible-run representation, independent point/line metrics, conservative accept/abstain/incorrect policy, detector replay and grouped JSON/Markdown reports. Detector defaults are read without loading .env; no production file edits.
- Initial focused test run: 26 passed, one synthetic background fixture failed because its rectangle exceeded the existing detector's 75% area safety limit. Corrected the fixture to stay below that limit; production behavior remains unchanged.
- Milestone 2: 30 focused tests pass, including actual detector replay of correct and >90%-confidence background geometry, projective transforms, unknown/occluded labels, line-only contradictions, leakage, integrity and byte-deterministic output. Scoped Ruff and mypy checks pass. Generated JSON Schema and a draft annotation template agree with the executable schema.
- Dataset manifest is intentionally empty: zero reviewed real labels in the new format. Existing 24 unique images are candidate material, not a representative benchmark.
- Added `calibration/court_vision/README.md` with the exact format, policy, runner commands and limitations. Foundation evaluates per-frame proposals against labels; automatic pixel-line extraction, temporal validation, model training and runtime integration are deferred, not implied by an accept outcome.
- Milestone 3: empty-manifest CLI smoke output was generated under ignored `data/output/court-vision-foundation-smoke-20261002`; it truthfully reports zero frames and no accuracy result. `git diff --check` passed and the production application/config diff remained empty at that checkpoint.
- Milestone 4: made empty-manifest evidence status explicit in JSON and Markdown: zero reviewed real examples, no real-world accuracy conclusion, and accepted-geometry correctness/support-view coverage gates not evaluated or claimed met. Two final empty-manifest runs produced byte-identical JSON and Markdown.
- Final validation: 30 focused tests passed; scoped Ruff lint and format checks passed; scoped mypy passed with no issues in three source files; final `git diff --check` passed. Production detector/workflow code, application behavior, configuration and permanent context documents remain unchanged.
- Phase 1 is complete and ready for the proposed 120-frame reviewed dataset pilot. Do not infer accuracy from synthetic tests or the empty manifest.

## Current audit progress
- Read AGENTS.md and previous handoff; working tree was clean before this documentation update.
- Current reported defect: high polygon-shape confidence can accompany incorrect court-floor geometry. Preserve the completed verification safety gate.
- Milestone 1: inspected automatic.py, four-point homography, Pickleball landmarks, sport policies, sampling, YOLO provisioning, review UI and verification tests. Shape scoring and best-single-frame selection are confirmed; numerical reprojection is not semantic validation.
- Existing reuse: 20 x 44 ft template, NVZ positions, projected overlays, sampled JPEG artifacts, separate generated/verified lifecycle and checksum-bound human confirmation. YOLO person weights are not court keypoint weights.
- Milestone 2: local inventory found 179 sampled JPEGs across 144 directories, with only 24 distinct SHA-256 contents. Both evidence manifests have two samples. Inspected landscape/portrait real frames and a blank validation fixture. Counts do not establish eligible or independent training examples; no remote inventory performed.
- Milestone 3: completed `docs/dev/PICKLEBALL_COURT_VISION_DESIGN_AUDIT.md`: 12 named floor landmarks, physical-line/edge convention, hybrid model recommendation, independent evidence checks, temporal agreement equations, data contract/splits, prototype targets, risks and phased plan.
- Recommendation: separate Pickleball keypoint proposal model plus deterministic line/template/temporal validation; preserve human confirmation and manual correction. No LLM/VLM geometric authority.
- Smallest Phase 1: offline-only label schema, deduplicated pilot benchmark, unchanged-detector replay, line validator and temporal diagnostics. No production integration or training in Phase 1.
- Proposed data budget: 120-frame pilot; 1,200-frame learned prototype (~800/200/200 grouped train/validation/test), with recording/venue separation and independent point/line labels. This is a planning estimate, not demonstrated sufficiency.
- Validation: audited source and tests without executing them; inspected local artifacts and official documentation. Documentation whitespace checks passed and git status confirms only this handoff and the new audit changed. No benchmark accuracy, training outcome or deployment readiness is claimed; no production files changed.
- The preceding milestones describe the completed design audit. Phase 1 is now authorized within the offline-only scope above. Do not stage, commit, push or deploy.

## Last completed task
Verified court calibration safety gate and concurrency protection.

## Last completed outcome
- Generated and verified calibration states are separate.
- Verification is bound to calibration ID and checksum.
- Recalibration invalidates stale measurements.
- Unverified calibration cannot feed downstream measurements.
- Manual calibration uses repository-managed workspace/S3.
- Stale concurrent saves are blocked by row-version checks.

## Next planned work
After separate authorization, establish usage/retention provenance for retained sources and obtain the additional independent recordings, courts, venues and conditions identified by the inventory. The 120-frame collection/review remains NOT STARTED; frame selection, extraction, labeling, detector evaluation, runtime integration and model training remain outside this task.

## Do not change without explicit instruction
- detector confidence formula or thresholds
- YOLO settings
- ByteTrack settings
- analytics formulas
- Match IQ formulas
- Padel gates
- ball tracking flag
- Railway variables
- storage limits
