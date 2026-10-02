# Current Court4 Task

## Status
COMPLETE — 120-Frame Reviewed Dataset Pilot Preparation (2026-10-02)

## Current task
Premium Pickleball Court Vision — prepare the 120-frame reviewed real-world dataset pilot protocol. Preparation only: no collection, labeling, training or production integration.

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
After separate authorization, inventory eligible sources and populate the candidate ledger under the protocol before copying or labeling frames. Runtime integration and model training remain outside this task.

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
