# Premium Pickleball Court Vision / Calibration Accuracy

Design audit, 2026-10-02. Status: **READY FOR IMPLEMENTATION PLANNING**.

This is a proposed design, not implemented or validated performance. Readiness applies to planning the offline Phase 1 below, not to shipping automatic acceptance. No production behavior, detector thresholds, calibration states, tracking, analytics, Match IQ, sport gates, ball tracking flag, storage limits or deployment configuration changes are authorized.

## Recommendation

Use a hybrid: a small Pickleball-specific keypoint model proposes named floor landmarks; deterministic template fitting, independently extracted visible-line evidence and agreement across stationary-camera frames assess the proposal. Preserve the current manual four-corner correction and checksum-bound human confirmation. A proposal that passes experimental validation is still unverified in Court4's existing lifecycle. No LLM/VLM has geometric authority.

Start with an offline evidence benchmark and deterministic validator around the current detector. This first establishes whether geometry is correct, measures current failure modes and creates reusable labels. Train a separate Ultralytics court-pose model only after this measurement foundation exists. Retain contour and line-only approaches as measured baselines rather than redesigning the production detector first.

## What the repository establishes

| Evidence | Finding and implication |
| --- | --- |
| `app/services/court_detection/automatic.py`: `_court_line_mask`, `_candidate_from_contour`, `_score_candidate`, `detect_pickleball_court` | HSV saturation mask or Canny edges, morphology, external contours, convex hull and four-point approximation produce proposals. Score is `0.20 + 0.55*area + 0.15*solidity + 0.10*side_balance`. Neither landmark identity nor internal line alignment is scored. Highest score across frames wins; there is no temporal consensus. A 96% score is not a calibrated probability of correct floor geometry. |
| Same file: `_order_corners` | Sorting by image y and then x assumes a familiar baseline view. Diagonal/side views and rotated images can produce incorrect correspondence even for a plausible polygon. |
| `app/sports/pickleball/calibration.py`: `calibrate_court` | Four ordered corners define the transform. Reprojection of those fitting points and numerical round-trip checks establish numerical consistency, not real-world correspondence. A wrong quadrilateral can pass. The image-bounds contract also prevents directly passing offscreen inferred corners to this path. |
| `app/sports/pickleball/geometry.py`, `landmarks.py` | Reuse 20 x 44 ft coordinates, kitchen lines at y=15 and y=29, and existing projection helpers. Overlay landmarks include a virtual net line and derived transition zones; these must not become required visible paint. Sidelines are currently drawn through the outer polygon, not named in the line tuple. |
| `app/services/jobs/workflow.py`: `detect_court`, `submit_calibration`, `confirm_calibration`; `app/schemas/calibration.py` | Generated geometry stays separate from verification. Confirmation binds calibration ID and file checksum. Correction invalidates prior measurements. Reuse this boundary without modifying it. |
| `web/components/calibration-review.tsx`, `manual-calibration-workspace.tsx` | Review already asks users to inspect outer and kitchen lines and exposes four-corner correction on a selected sampled frame. Preserve this fallback. |
| `app/services/video/inspector.py`, workflow `list_sampled_frames` | Sampled JPEGs are existing artifacts. Filenames encode one-based frame numbers; nominal timestamp is `(frame_number-1)/fps`. Preserve decoded dimensions, rotation/crop provenance and source identity, and verify timing against source where variable frame rate matters. |
| `pyproject.toml`, `app/services/tracking/model_provisioning.py`, `ultralytics_bytetrack_backend.py` | Optional Ultralytics `>=8.3,<9.0`, NumPy and OpenCV are available architectural choices. Existing pinned `yolo11n.pt` detects people; it is not a trained court-pose model. Reuse library and checksum/provisioning patterns, not the stateful ByteTrack adapter or its settings. |
| `app/sports/config.py`, `app/sports/padel/geometry.py` | Sport versions and policies exist. Padel has different geometry/units and all relevant capabilities remain disabled. |
| `tests/test_court_detection.py`, `test_court_calibration.py`, `test_calibration_verification.py` | Existing coverage addresses borders, decode failures, synthetic transform validity and verification lifecycle. It does not establish accuracy on a diverse independently annotated real-court benchmark. |

The user-reported 96%+ failure was not reproduced as a new run in this audit. The code explains how it can occur; no new accuracy result is claimed.

## Landmark and paint contract

Use one `pickleball_court` instance with these **12 ordered keypoints**, expressed in existing Court4 feet coordinates. Near/far refer to camera-relative court ends, not teams. Left/right follow the selected near-end convention. Reject unresolved orientation; do not infer it merely by sorting y. Lock the convention per stationary shot. Limit the first model's supported proposal envelope to baseline and moderate diagonal views; retain side-on/ambiguous views for abstention testing.

| Index | Name | Court coordinate | Value and visibility expectation |
| --- | --- | --- | --- |
| 0 | near_left | (0, 0) | Outer corner; often strong, but may be cropped |
| 1 | near_right | (20, 0) | Outer corner; often strong, but may be cropped |
| 2 | far_right | (20, 44) | Extent constraint; small, obscured or confused with adjacent courts |
| 3 | far_left | (0, 44) | Extent constraint; same limitations |
| 4 | near_nvz_left | (0, 15) | Sideline/NVZ intersection; high semantic value |
| 5 | near_nvz_right | (20, 15) | Sideline/NVZ intersection; high semantic value |
| 6 | far_nvz_left | (0, 29) | Distinguishes full court from service boxes; net/player occlusion risk |
| 7 | far_nvz_right | (20, 29) | Same |
| 8 | near_baseline_center | (10, 0) | Service centerline/baseline T junction |
| 9 | near_nvz_center | (10, 15) | Service centerline/NVZ T junction; useful semantic cross-check |
| 10 | far_nvz_center | (10, 29) | Same, with weaker distant visibility |
| 11 | far_baseline_center | (10, 44) | Same, with weaker distant visibility |

These visibility rankings are design expectations, not measured detection rates. Measure labelability by landmark on the seed set. Eight outer/NVZ side intersections supply width and depth; four T junctions add topology and redundancy. Do not force every landmark visible or train guesses as observed evidence.

The canonical physical definition uses the **outside perimeter edges** for x=0/20 and y=0/44; NVZ y=15/29 is the boundary edge farther from the net. Center-service x=10 follows the stripe center. Annotate the corresponding intersections of these specified axes, not arbitrary centers of thick paint blobs. USA Pickleball specifies 20 x 44 ft, 7 ft NVZ depth and outside-edge measurements; preserve a versioned annotation convention. [USA Pickleball construction guidance](https://usapickleball.org/construction/), [official 2025 rulebook, court geometry](https://usapickleball.org/docs/2025-USA-Pickleball-Rulebook.pdf).

Annotate eight physical line identities: two baselines, two sidelines, two NVZ lines and two service centerlines (only baseline-to-NVZ, never through the kitchen). Record visible runs, selected reference edge/center and local paint width/uncertainty. A net's top tape, posts, shadows and virtual floor projection are not coplanar painted landmarks. Exclude them from homography constraints. Do not validate derived transition zones as paint. Color alone is not an identity cue.

## Why hybrid first

| Method | First-upgrade assessment |
| --- | --- |
| Line detector + template search | Cheapest offline baseline and useful verifier; fragmented paint and tennis/basketball markings create many ambiguous assignments. Do not assume it alone solves semantic identity. |
| Keypoint model alone | Efficient named correspondence prediction and modest annotation cost, but can hallucinate hidden corners or repeat a consistent wrong court. Proposal source only. |
| Full semantic segmentation | Dense evidence may help worn/colored lines later, but pixel labeling and thin-line class imbalance add cost. A floor-region mask still need not identify correct court boundaries. Defer until measured line-verifier failures justify it. |
| Keypoints + deterministic line/template/temporal checks | Recommended first learned upgrade. Reuses the stack while separating recognition from acceptance evidence. |

Use a separate YOLO11-compatible small pose checkpoint with a custom 12-point head, independently versioned from person tracking. Benchmark nano first and small only if needed. Pin exact training/runtime versions and weight hash in experiment manifests; the repository dependency range is not a reproducible training environment. No model downloads or dependency changes in this audit.

Ultralytics supports custom pose labels with bounding boxes, normalized keypoints and visibility plus `kpt_shape`/`flip_idx`. Proposed export: `kpt_shape: [12,3]`, class 0, horizontal flip map `[1,0,3,2,5,4,7,6,8,9,10,11]`. Keep richer provenance in JSON; test exporter/augmentation behavior against the pinned version. Disable vertical flips and composite augmentations initially; near/far identity must survive any transform. [Ultralytics pose data format](https://docs.ultralytics.com/datasets/pose/). Its pose training/inference interface can host the custom model; generic pretrained human keypoints do not supply court semantics. [Ultralytics pose task](https://docs.ultralytics.com/tasks/pose/).

## Proposed evidence flow and independent validation

1. Select 5-9 temporally spread, nonduplicate samples within one stationary shot, where available. Assess blur, clipping and court visibility. Retain poor/negative frames in the benchmark rather than silently removing failures. Sparse single-frame cases cannot earn multi-frame support.
2. Produce named point proposals per court instance. Preserve keypoint uncertainty, missingness and alternate hypotheses. Multiple equally plausible courts trigger ambiguity/manual selection, not a larger-polygon preference.
3. Fit image-to-template homography robustly from a distributed subset of observed landmarks. Four noncollinear correspondences are the algebraic minimum, not an acceptance standard. Initially require at least six observed, spatially distributed points spanning both halves and both sides, plus line evidence below. Check convexity, ordering, rank/conditioning, finite projections and sensitivity to landmark perturbations. OpenCV offers robust `findHomography`; its inlier residual remains a fitting statistic. [OpenCV homography API](https://docs.opencv.org/4.x/d9/d0c/group__calib3d.html).
4. Independently extract line/edge candidates from the original decoded image using OpenCV segment/edge tools, not the model's heatmaps or the old dilated contour mask. Compare projected physical paint against line orientation, continuity, width and distance. Match paint bands/reference edges explicitly, so two edges of one stripe do not count twice. Detect evidence before scoring a proposal; use the projection only for correspondence search.
5. For each line, sample equal-length bins along its visible projected span. Compute supported fraction, median and p90 perpendicular distance, orientation residual and longest unsupported run. Exclude independently established occlusions/out-of-frame spans and report the remaining measurable length. No observed evidence means unknown, never a perfect score. Do not let the proposing model declare every mismatch occluded.
6. Require distributed support: both NVZ lines, both side boundaries and both baselines, allowing fragmented visible runs. A conservative prototype starts with at least 30% measurable length and 70% support within that length for each required line; tolerances are resolution/paint-width-aware and must be selected on development/validation data. Center-service segments provide extra semantic checks when visible. This deliberately abstains on many partial views. Record insufficient visibility separately from contradiction.
7. Keep fitting and validating evidence distinct. Reserve line interiors away from keypoint intersections and at least one spatially useful landmark subset for checks; use leave-group-out fits to expose dependence. Any later line-based refinement must reserve different runs/frames for validation. Fixed template ratios and low fit residual alone are circular evidence. Deterministic image checks are a separate evidence channel, not statistically independent ground truth; human-reviewed holdout labels remain essential.
8. Report an evidence vector: landmark coverage, withheld errors, each line's support, ambiguity, perturbation sensitivity, temporal support and explicit failure reasons. Use conjunctions of required checks, not a weighted average that lets confidence cancel a missing kitchen line. Any display score is an experimental quality index, never a correctness probability without separate calibration data.

Ground truth is independently labeled visible points and line runs, not an automatic overlay or the four corners previously clicked by a user. For benchmark projection error, withhold landmarks from fitting and compare their measured pixel positions to template projections; also map these held-out labels into feet. Interior line evidence is necessary even when outer-corner labels look plausible. Annotators should first label the original frame without seeing the detector proposal. Fit a reference transform only for adjudication/diagnostics and keep its fitting inputs separate from evaluation targets.

Lens distortion, severe perspective and non-flat surfaces can break a single homography. Estimate local sensitivity by perturbing labels within their recorded uncertainty and measuring a fixed court-grid displacement distribution. Abstain when the transform is poorly constrained; do not add camera-intrinsic estimation to the first prototype.

## Multi-frame agreement: explicit score proposal

Compare projected geometry, not raw homography coefficients. Let `P_i(q)` project court point q into frame i; use the 12 landmarks plus a fixed 5 x 5 interior grid, and `D` as image diagonal. For same-size frames in a confirmed stationary shot:

`d(i,j) = percentile90_q(||P_i(q)-P_j(q)|| / D)`.

Use only finite, well-conditioned projections; common coverage must span the court, otherwise agreement is unavailable. Cluster proposals using a maximum cluster diameter (complete-link), initially `d <= 0.005`, to prevent a chain of drifting frames looking stable. These are experimental settings, not replacements for production thresholds.

Choose the dominant cluster's medoid, then define:

- `A = number of temporally distinct, individually line-supported frames in cluster / number of decodable sampled frames in shot` (failed detections remain in the denominator).
- `J = p90 of d(frame, medoid)` within that cluster.
- `T = A * max(0, 1 - J / 0.005)`, a diagnostic index only.

Prototype temporal pass additionally requires at least three supported frames from separated time bins, `A >= 0.70`, `J <= 0.003`, no rival supported cluster containing 20% or more of decodable frames, and no detected camera change. Duplicated frames do not increase evidence count. Per-frame line checks must pass independently; a stable wrong polygon is still wrong. Report sample times and gaps; sparse samples do not prove intervening frames stable.

Detect cuts/pan/zoom using background registration and segment-level evidence before comparing geometry. For the first prototype, motion/registration uncertainty causes abstention; do not average across shots. Later registration could bring frames into a reference plane, with its own uncertainty. Prefer the medoid proposal or robust joint landmark fit, never elementwise averaging of homography matrices. Evaluate beginning/middle/end coverage; a single confirmed view cannot establish whole-video validity after camera movement. Changing runtime calibration lifecycle for moving cameras is outside this plan.

## Data inventory and exact annotation requirements

Local read-only inventory on 2026-10-02 found **179 sampled JPEGs in 144 frame directories, only 24 distinct SHA-256 contents** under `data`. These are file counts, not independent courts, recordings or usable training examples. Both `calibration/manifest.v1.json` and `.v2.json` contain two samples; they are versions, not four independent videos. Their linked landscape recording has three local frames and the portrait recording one. The existing evidence-calibration schema describes recording/tracking/insight reviews, not a 12-landmark training set; keep the court-vision dataset separate and link provenance.

Visual inspection of one landscape frame showed competing adjacent-court markings, players and net obscuring distant geometry. The portrait frame showed cropping, strong lighting and a text overlay. A validation-run frame was a tiny blank image. These demonstrate seed/rejection cases, not population statistics. No production/S3 inventory or training-use eligibility review was performed.

Existing sampled frames **can seed** the dataset after provenance/usage eligibility, deduplication and human labeling. Do not use confidence scores, auto corners or existing confirmation as ground truth. Retrieve any future remote artifacts through owner/lifecycle/checksum-aware repository access; do not scan shared buckets or resurrect deleted media. Store experiment outputs separately in a repository-managed workspace, not legacy hardcoded `/app/data/output`. No dataset export took place in this audit.

Required authoritative JSON record per frame:

- Dataset/schema/template/annotation convention versions; frame and source-video hashes; analysis/artifact reference; authorized dataset-use provenance and retention handling; recording, venue, physical court, camera-setup and shot group IDs; locked split.
- Frame number, nominal/verified timestamp, original decoded width/height, rotation, crop/resize transform and image hash. Labels live in original decoded pixels; exporters transform explicitly.
- Every discernible court instance, its box enclosing visible court extent, target-court identity if known, sport and orientation convention. Exclude ambiguous partially visible instances from pose training when they cannot be labeled; retain frame in abstention evaluation. Never silently treat an unlabeled visible court as background.
- All 12 keypoint entries: name, nullable x/y, `visible`, `occluded_localizable`, `outside_frame` or `unknown`, pixel uncertainty, annotation provenance. Infer an occluded point only when adjacent visible geometry localizes it, marking it as inferred; it cannot count as observed support. Unknown/offscreen labels export as visibility 0 with placeholder coordinates, localizable occluded as 1, visible as 2. Confirm the chosen trainer's treatment of visibility 1; do not assume it suppresses coordinate loss.
- Eight semantic line records with visible reference-edge/center polylines, visible intervals, paint width and uncertainty; explicit occlusion/offscreen/unknown intervals. No invented line behind a player or net. Annotate all pilot/evaluation frames; training-only line labels can be added in a later targeted tranche if cost dominates.
- Indoor/outdoor, paint colors, competing sports/adjacent courts, camera angle/height, resolution, lighting/glare, blur, cropping, occlusion, motion/cut, distortion and nonstandard geometry tags; suitability `full_geometry_supported`, `partial_or_ambiguous`, or `no_target_court`, with reasons.
- Annotator/reviewer IDs, review status, disagreements and adjudication. Double-label all validation/test frames and 20% of training. Adjudicate disagreements above 0.3% image diagonal or an annotation-uncertainty overlap failure; unresolved points remain unknown.

No dense segmentation masks are required initially. Line-run labels are lightweight evaluation evidence, not a segmentation-model commitment. Empty pose labels are allowed only for reviewed true negatives. Keep synthetic transform fixtures separate from real-camera accuracy evaluation.

### Proposed collection size and splits

These are budgeting hypotheses, not literature-backed sufficiency claims. Independent camera/venue diversity matters more than adjacent frame count.

- Phase 1 labelability/validator pilot: **120 distinct real frames**, approximately 20 independent recording/camera groups, 4-8 spaced frames per group, targeting at least eight venues. Include at least 30 partial/ambiguous/negative frames and the reported high-confidence failures if available. Use approximately 80 development/40 evaluation frames with whole-group separation; this pilot is not a production reliability claim.
- First learned prototype: **1,200 labeled frames**, approximately 120 recording/camera groups across at least 20 venues, normally 5-10 useful spaced frames per group. Target roughly 900 positive court frames and 300 challenging partial/ambiguous/negative frames; report their separate counts. Some challenge frames will be evaluation-only. Begin a learning-curve checkpoint at 400-600 training labels before spending the full annotation budget.
- Allocate approximately **800 train / 200 validation / 200 frozen test** by groups, not exact image quotas at the expense of independence. Group all near-duplicate recordings, physical court/camera setups and venue clusters together where feasible; reserve at least four unseen venues for the frozen test. No adjacent frames or augmented versions may cross splits. Synthetic data is train-only. Pilot evaluation data used for design becomes development data, never the final unseen test.
- Cover indoor/outdoor, white/colored/worn paint, baseline/diagonal, singles/doubles, distant/low cameras, 720p/1080p plus low-resolution stress, glare/shadows, players/net occlusion, overlays, cropped courts, neighboring courts and other-sport paint. Require at least 20 tagged examples per major stress category overall; overlapping tags are allowed. Report absent slices instead of claiming coverage. Include at least 20 held-out temporal sequences of 5+ frames for agreement evaluation; these frames count toward the total.

The local inventory is insufficient to meet this plan. Additional eligible recordings and annotation work are prerequisites for model training, not blockers to planning the offline harness.

## Prototype success criteria

All numbers below are proposed offline acceptance targets to ratify in planning. Select tolerances on development/validation, then freeze before test; never tune on test. Report counts and confidence intervals by independent recording/venue as well as frame. No pass is claimed here.

| Criterion | Proposed gate |
| --- | --- |
| Phase 1 validator | Reproducible original-detector baseline; reject all curated known wrong-geometry cases, including wrong NVZ/full-court swaps and stable wrong polygons; retain at least 80% of independently correct, fully visible pilot proposals. Report uncertainty; a small pilot cannot prove rare-error safety. |
| Landmark accuracy | On visible independently labeled test points, median error <=0.3% and p95 <=0.8% of image diagonal; report near/far and each landmark separately. This alone is not a geometry pass. |
| Geometry correctness | An accepted proposal must have correct court/orientation, no contradicted outer/NVZ topology, p95 withheld-landmark projection error <=0.5% diagonal and p95 held-out court-coordinate error <=0.5 ft within the supported region. Report far-half errors and extrapolation separately. Inadequate independent labels make it unscorable, not correct. |
| Precision and useful coverage | >=98% correctness among accepted, scorable test proposals and >=60% acceptance on independently adjudicated full-geometry-supported frames. Report acceptance over all inputs too. Compare baseline, baseline+validator, keypoint-only and hybrid at matched coverage and matched precision. Aim for >=50% fewer wrong accepted proposals at matched coverage; if baseline has no measured errors, do not claim a relative reduction. |
| Temporal behavior | Pass the explicit A/J/count rules above on supported stationary sequences; abstain on all curated cut/pan/zoom and stable-wrong-geometry cases. Measure false stability across the full test set; sparse sequences remain limited. |
| Abstention | Separately report false acceptance on no-court/other-sport/ambiguous/cropped inputs; no acceptance of curated wrong-plane, wrong-court or unsupported orientation cases. Unscorable accepted outputs count as unsupported acceptance, not precision successes. |
| Operational boundary | Offline runs make zero job/calibration/database changes. Record model/version/hash, dataset/split hash, hardware, latency and peak memory. Before any integration, agree a measured resource budget on intended hardware; none is established by this audit. |

The prototype's roughly 200 test frames cannot establish a sub-1% real-world failure rate. Even zero errors needs about 300 independent accepted cases for a one-sided 95% upper bound near 1%; correlated frames reduce effective evidence. Later rollout needs expanded independent validation, not multiplying frames from the same video. Human confirmation stays mandatory throughout this proposed upgrade path.

## Deterministic boundaries and sport reuse

Learn appearance-to-landmark identity and localization only. Keep court dimensions, units, correspondence topology, transform fitting, numerical checks, line-support scoring, temporal aggregation, uncertainty/abstention rules, artifact provenance and verification deterministic and versioned. A later learned line mask remains evidence to validate, not authority to self-approve geometry.

Start with a small experiment-local template contract: sport ID, definition version, units, named points, physical painted segments, virtual segments, supported view conventions and valid symmetry mappings. Populate only Pickleball using existing definitions; avoid restructuring the runtime sport architecture. A reusable fitter/validator can consume this contract later. Padel requires its own landmarks, units, visibility rules, weights/data and wall/reflection treatment; do not alias NVZ semantics to service lines or transfer acceptance thresholds without evaluation. Existing Padel gates remain closed and `BALL_TRACKING_ENABLED=false` remains unchanged.

## Phased implementation plan

| Phase | Deliverable | Exit / scope boundary |
| --- | --- | --- |
| 1: offline evidence foundation | Versioned annotation contract, local inventory/dedup/split tooling, pilot labels, original-detector replay, independent visible-line evaluator, evidence overlays/JSON and simple stationary-frame agreement report | Pilot results and failure review are reproducible; no runtime imports of the experiment, API/UI/state/config changes, model training or deployment |
| 2: learned proposal experiment | Separate small 12-point Ultralytics model, frozen split, robust template fitting and ablations against Phase 1 | Geometry, precision/coverage and temporal targets measured; resource and data limitations explicit |
| 3: refine only measured weaknesses | Targeted annotation/active sampling; possibly line segmentation or better distortion handling if failures justify it | Demonstrated improvement on newly reserved holdout; no redesign based only on preference |
| 4: separately authorized integration | Adapter returning the existing ordered four-corner proposal on supported in-frame cases; existing overlay/manual review and checksum verification | Review adapter precision loss from reducing a many-point fit to four corners; retain diagnostic evidence separately. All lifecycle, ownership, concurrency and sport safeguards remain intact. Offscreen corners/moving cameras stay unsupported pending separate design. No automatic promotion to verified |

### Smallest safe Phase 1 implementation

Propose new offline-only files under `scripts/`, `calibration/court_vision/` (schema/manifest instructions, no committed private media) and focused tests. Final filenames belong to implementation planning. Do not edit `automatic.py`, workflow, schemas used by production, UI, sport policies, configuration or dependencies for Phase 1.

1. Define the JSON label contract and renderer; inventory explicitly supplied eligible local artifacts, hash/deduplicate, and group source recordings. Manually label/adjudicate the pilot, including internal lines.
2. Wrap the unchanged current detector in an offline runner with isolated scratch output. Preserve its original scores and thresholds. Store proposed corners/results separately from human labels. Never register outputs as active calibrations.
3. Add deterministic projected-line evaluation, withheld-label error reporting and same-shot agreement diagnostics. Emit `supported`, `contradicted` or `insufficient_evidence` plus per-line reasons; do not write `verified`.
4. Compare baseline and validator results with review overlays and repeatable JSON summaries. Include high-confidence wrong quadrilaterals, correct courts, missing paint, false-colored rectangles, service-box/full-court confusion, net-top alignment, partial views and stable wrong proposals. Export no dataset or weights to external services.
5. Add only distinct tests for annotation/order/export, line-edge convention, split leakage, known semantic misalignment, absent evidence, stable wrong geometry and camera-change abstention. Reuse existing numerical/lifecycle coverage instead of duplicating it. Run focused new checks; run existing safety suites only if later integration touches those paths.

## Main risks and remaining decisions

- Data scarcity and repeated camera views can give falsely strong results. Local files do not establish training permission, diversity or enough labels.
- Occlusion, cropping and distant far lines may force high abstention. Manual correction helps only when a usable view exists; it cannot recover unobservable evidence.
- Paint thickness/edge conventions, neighboring courts and nonstandard layouts can cause systematic errors despite high keypoint confidence.
- Learned proposals and deterministic line checks can share appearance failures; human held-out evidence and explicit negative cases remain necessary.
- Perspective symmetry can swap ends/sides; wide lenses and camera motion can invalidate a single-plane mapping. Temporal consistency alone cannot resolve a consistently wrong interpretation.
- A 12-point fit reduced to four corners may lose some accuracy; measure before using the current calibration entry point. Do not change that API speculatively.
- The initial collection size, pixel/feet tolerances and latency budget need empirical confirmation. Phase 1 resolves labelability and validation feasibility; Phase 2 decides whether the learned upgrade is useful.

Audit validation: source/code inspection, local frame counts and SHA-256 deduplication, selected image inspection, official format/API/geometry references and final documentation diff checks. No training, inference benchmark, new tests or production operations were run. **READY FOR IMPLEMENTATION PLANNING** for offline Phase 1 only.
