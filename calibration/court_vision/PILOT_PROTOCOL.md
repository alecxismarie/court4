# Pickleball Court Vision 120-frame pilot protocol

Status: preparation protocol only. No real frame has been selected, copied, annotated, reviewed, or added to the benchmark manifest by this document.

## Purpose and authority

The pilot will measure how the unchanged current Pickleball court detector behaves on a controlled first sample of realistic Court4 recordings. It asks whether a proposal is geometrically supported by independently reviewed court evidence and when the system should abstain. It is an evaluation dataset, not authorized training data.

The executable annotation authority remains `scripts/court_vision_annotations.py`; `annotation.schema.json`, `frame-template.v1.json`, and the Phase 1 evaluator remain unchanged. This protocol controls selection and human review. Detector output, confidence, existing automatic corners, verification overlays, and prior user confirmation are never ground truth.

The pilot is not globally representative. It cannot establish a population failure rate, production readiness, or automatic verification safety. Missing conditions must be named in the final diversity report.

## Exact 120-frame sampling structure

Assign each selected candidate to exactly one primary sampling stratum before annotation. The stratum describes why the frame was sampled; it does not dictate the annotator's later `suitability` decision.

| Primary stratum | Frames | Selection intent |
| --- | ---: | --- |
| Routine supported-view candidates | 50 | Complete, normally visible Pickleball courts from ordinary centered or modestly diagonal Court4-style recordings, including visually clean and typical-play frames. |
| Challenging supported-view candidates | 40 | Frames still expected to be labelable but containing realistic difficulty such as moderate diagonal perspective, lower contrast, worn paint, shadows/glare, player or net occlusion, competing markings, or modest cropping. |
| Partial or ambiguous abstention candidates | 20 | Cropped, heavily occluded, multi-court ambiguous, orientation-uncertain, moving-camera, severe-perspective, or otherwise incomplete views where correct abstention may be preferable. |
| No-target or visual-decoy candidates | 10 | Reviewed negatives: no target Pickleball court, another sport's markings, a non-court rectangle, or an unusable image. Do not include a discernible but unlabeled target court as a negative. |
| **Total** | **120** | 90 supported-view candidates and 30 partial/ambiguous/negative candidates. |

Do not force the final label to preserve these expected suitability counts. If independent review changes a candidate's interpretation, record the change. Replace a candidate before manifest freeze only to restore the sampling design, never because the current detector performed poorly on it. Keep replacement and exclusion reasons in the pilot ledger.

### Independence and contribution limits

- Use at least 20 distinct `recording_id` + `camera_setup_id` groups. Target 20-24 groups contributing about 5-6 frames each.
- A source recording may contribute at most 8 of the 120 scored frames, even if it contains camera cuts or multiple shots.
- A single stationary `shot_id` may contribute at most 6 frames.
- A physical `court_id` may contribute at most 16 frames.
- A `venue_id` may contribute at most 24 frames. If too few eligible venues exist, do not invent venue diversity; disclose the shortfall before collection is declared complete.
- Prefer at least eight venues and at least twelve physical courts where eligible sources permit. These are diversity goals, not permission to use ineligible media.
- Exact duplicate image hashes are prohibited among the 120 scored frames. An intentional duplicate used for process QC stays outside the scored manifest.

Within a recording, sample across time and visible conditions instead of taking adjacent frames. Normally separate selected frames by at least 10 seconds and use beginning, middle, and end portions of a stationary shot. For a short recording, a frame may be closer only when it differs materially in occlusion, lighting, camera state, or court visibility; never select frames less than 2 seconds apart merely to reach a quota. Record timestamps and selection reasons. A cut, pan, zoom, camera relocation, resolution/orientation change, or material field-of-view change starts a new `shot_id` and usually a new `camera_setup_id`.

### Required versus desired diversity

Required:

- the four primary-stratum counts above;
- at least 20 recording/camera groups and the contribution caps above;
- all 120 images have distinct SHA-256 hashes and eligible provenance;
- both routine and difficult real usage, plus explicit abstention/negative cases;
- no selection based on detector success, failure, confidence, or overlay appearance.

A failure case documented before pilot selection may be included as a declared challenge case, including the previously reported high-confidence geometry failure if eligible source media exists. Record that selection provenance and count it within the fixed challenging/abstention strata. Do not run the detector to discover additional cases while selecting the remaining sample.

Desired where eligible sources exist:

| Dimension | Desired coverage; tags may overlap | Actual count | Missing/limitation |
| --- | --- | ---: | --- |
| Environment | Indoor and outdoor; aim for at least 30 of each | TBD | TBD |
| Court/paint | Multiple floor colors; white and colored/worn line paint | TBD | TBD |
| Lighting | Even light plus at least 20 tagged shadow, glare, mixed, or low-light frames | TBD | TBD |
| Camera view | Centered baseline and at least 30 moderate-diagonal frames | TBD | TBD |
| Camera height | Low, typical, and elevated where known | TBD | TBD |
| Occlusion | Clear plus at least 20 frames with meaningful player/net obstruction | TBD | TBD |
| Competing markings | At least 20 frames with adjacent-court or other-sport markings | TBD | TBD |
| Cropping | Complete court plus partial cropping in the abstention stratum | TBD | TBD |
| Resolution/distortion | Available 720p/1080p and moderate lens/perspective stress | TBD | TBD |

Use stable controlled tag prefixes in `tags`: `environment:`, `court_color:`, `line_contrast:`, `lighting:`, `camera_height:`, `camera_view:`, `crop:`, `occlusion:`, `competing_markings:`, and `difficulty:`. Free-text `reasons` explain facts that the tags cannot. Never claim a dimension was covered when the sources do not contain it.

## Grouping, hashes, and future leakage control

Identifiers are opaque, stable dataset identifiers and must not contain player names, emails, account IDs, or other unnecessary personal information.

- `recording_id`: one source recording. Every frame from the same source bytes uses the same ID.
- `source_video_sha256`: hash the source bytes when legitimately available. If unavailable, leave it null and explain why in `source_reference`; never invent a hash.
- `shot_id`: one continuous interval without a cut or material camera change.
- `camera_setup_id`: one physical camera placement, orientation, lens/zoom, and decoded presentation. A relocation or material view change gets a new ID. If equivalence across recordings is unknown, use distinct IDs and document the uncertainty.
- `court_id`: one physical court where known. Reuse it across recordings only when that identity is supported.
- `venue_id`: one physical facility where known. Unknown venues get source-scoped unknown IDs rather than a shared `unknown` value that falsely groups unrelated places.
- `image_sha256`: SHA-256 of the exact decoded image file supplied to the benchmark. Recompute after any authorized derivation.

All pilot records use `split: development`. This is an administrative choice because no training split is authorized. Do not manufacture train/validation/test partitions. If model development is authorized later, reassign entire recording, source-video, court, camera-setup, and venue-related groups together. Exact image hashes and derived/augmented versions must never cross splits. The 120-frame pilot has already influenced design and must become development evidence, not a future frozen unseen test.

The Phase 1 leakage warnings remain required, but zero warnings do not prove independence: inconsistent identifiers and visually near-duplicate frames require human review. Report frame counts alongside distinct recording, camera, court, and venue counts so 120 frames are never described as 120 independent conditions.

## Orientation convention

Coordinates refer to the exact decoded image: origin at its top-left, x increasing rightward, and y increasing downward. Apply any documented rotation/crop/resize before annotation and never transform the image afterward.

1. **Near versus far:** `near` is the physical baseline at the court end closest to the camera position for the selected target court. `far` is the opposite physical baseline. Do not decide near/far only by sorting image y coordinates.
2. **Left versus right:** after the near baseline is identified, `near_left` is its endpoint with the smaller decoded-image x coordinate and `near_right` is the endpoint with the larger decoded-image x coordinate. Left/right therefore means decoded-image left/right, not a player's handedness, team side, compass direction, or the view from someone standing on court.
3. **Preserve topology:** `far_left` is the far endpoint reached by following the same physical sideline from `near_left`; `far_right` follows from `near_right`. Do not relabel far endpoints independently by apparent x if that would cross the court topology.
4. **Diagonal views:** use the physical closest baseline first, then decoded-image x on that baseline. Perspective may make endpoints differ greatly in y; that does not change left/right.
5. **Unresolvable views:** if the closest court end, selected target court, or noncrossing correspondence cannot be determined confidently from the original image and provenance, set `orientation: unresolved`, use `partial_or_ambiguous`, explain the reason, and never force a mirrored choice. The Phase 1 evaluator will abstain.

Typical baseline or moderate-diagonal view:

```text
decoded image: x increases →, y increases ↓

          far_left +----------------------+ far_right
                   |  far NVZ / service   |
                   |-------- net ---------|
                   |  near NVZ / service  |
         near_left +----------------------+ near_right
                         camera side

ordered outer corners: near_left → near_right → far_right → far_left
```

This convention preserves the existing Court4 order and 20 x 44 ft template. Side-on, severely rotated, or symmetry-ambiguous views are abstention evidence unless the physical near end is independently known.

## Annotation instructions

Annotators work from the original benchmark image without detector proposals, confidence, calibration overlays, or auto-generated points.

### Keypoints

Use all 12 existing names and coordinates. Outer corner points are intersections of the specified outside perimeter edges. NVZ side and center points use the NVZ paint edge farther from the net at y=15 or y=29. Center-service points use stripe center. Do not label the net, net shadow, transition-zone boundary, or an arbitrary edge of thick paint.

- `visible`: the specified semantic intersection is directly supported by image pixels. Supply `xy` and honest pixel uncertainty.
- `occluded_localizable`: the point is hidden, but adjacent visible geometry supports an inferred location. Supply `xy` and uncertainty; the evaluator deliberately excludes it from observed support.
- `outside_frame`: the semantic point lies outside the decoded image. Do not provide coordinates or uncertainty.
- `unknown`: the point cannot be localized reliably for any other reason. Do not provide coordinates or uncertainty.

Never promote an inferred, guessed, detector-suggested, or symmetry-assumed location to `visible`. High uncertainty is not a substitute for `unknown`.

### Lines and difficult frames

Annotate only directly visible runs of the eight physical lines. Outer lines use `outside_perimeter`; NVZ lines use the edge away from the net; center-service lines use stripe center and stop at the NVZ. Break a run at a player, net/post, glare patch, crop, or other occlusion. Empty visible runs plus the correct missing-evidence reason represent a line that cannot be observed. Competing markings are never target-court evidence merely because they align with a proposal.

Use `full_geometry_supported` only when the target and orientation are resolved and enough distributed geometry is genuinely visible for evaluation. Use `partial_or_ambiguous` for cropped, unresolved, or insufficient evidence, retaining every supportable label. Use `no_target_court` only when review establishes that the selected image has no target Pickleball court; all target keypoints must then be unknown and all target line runs empty. A visible court that is hard to label is not a negative.

## Independent review and adjudication

The schema stores the final label plus annotator/reviewer identities; it does not retain structured disagreement history. Use `pilot-review-ledger.template.csv` as the backward-compatible selection and review sidecar. It is process evidence, not benchmark geometry and is not added to `manifest.v1.json`.

Use these ledger values consistently:

- `sampling_stratum`: `routine_supported`, `challenging_supported`, `partial_or_ambiguous`, or `no_target_or_decoy`;
- `selection_status`: `candidate`, `selected`, `excluded`, `replaced`, or `frozen`;
- `review_state`: `not_started`, `draft`, `review_pending`, `disagreement`, `adjudication_pending`, or `reviewed`;
- `adjudication_state`: `not_required`, `pending`, `resolved`, or `unresolved`;
- `derivation`: `none` or a reproducible rotation/crop/resize description; and
- multi-value tag/disagreement cells: sorted semicolon-separated values, with commas quoted according to CSV rules.

Copy the diversity table into the versioned pilot completion report and fill its actual/missing columns; do not rewrite desired counts after seeing detector results.

1. **Selection coordinator:** records eligibility, grouping, source integrity, sampling stratum, derivation, and selection reason without running or viewing detector output.
2. **Annotator A:** labels the original image, applies the orientation convention, records uncertainty/tags/reasons, and leaves `review_status: draft`.
3. **Reviewer B:** a different person independently inspects the original image before viewing detector output. They check target identity, orientation, every visibility state, semantic point/line placement, uncertainty, suitability, tags, provenance, and group IDs. Disagreements go in the ledger; merely changing the JSON without a record is not review.
4. **Adjudication:** required for target/orientation/suitability disagreement; any visibility-category disagreement; wrong semantic line/reference edge; point differences greater than 0.3% of image diagonal; nonoverlapping uncertainty regions; or material line-run disagreement. A designated adjudicator may change the final JSON after reviewing both rationales. Prefer a third person; if unavailable, record a documented A/B consensus and that limitation.
5. **Unresolved evidence:** remains `unknown`, `outside_frame`, `orientation: unresolved`, or `partial_or_ambiguous`. Agreement must never be forced. A frame may be fully reviewed while still containing unknown evidence.
6. **Completion:** set `review_status: reviewed` only after Reviewer B and any required adjudication are complete. The schema's `reviewer` is the final independent reviewer and must differ from `annotator`. The ledger records adjudicator and resolution status.

Only the assigned annotator may submit the initial geometry; only the assigned reviewer/adjudicator may approve or alter the final reviewed geometry. Detector output is not shown until the complete 120-frame manifest and ledger are frozen and hashed.

## Provenance and derivation

For every candidate, record the schema-required source reference, usage eligibility/retention basis, group IDs, frame number, timestamp and its basis, decoded width/height, image hash, and source-video hash where available. The ledger additionally records selection status/stratum, derivation, reviewer/adjudicator state, disagreement summary, and exclusions.

Prefer the original sampled artifact without transformation. If rotation, crop, or resize is necessary, preserve the original reference; record the exact operation and original dimensions in the ledger and `source_reference`; hash the derived image; label only its final pixels; and do not mix original and derived copies as independent frames. No unnecessary player identity or biometric information is collected.

## Pilot completion gates

The pilot may be called **reviewed** only when all checks pass:

- exactly 120 scored manifest frames, all `data_kind: real`, with the primary ledger strata totaling 50 + 40 + 20 + 10;
- the committed empty manifest was not populated during preparation; collection uses a separately frozen/versioned pilot manifest when authorized;
- all 120 image hashes are unique, files decode to declared dimensions, and hashes match; duplicates used for QC are excluded from the scored 120;
- every record validates against the Phase 1 executable schema and fixed version strings;
- provenance/usage eligibility, source reference, grouping IDs, timestamp basis, and derivation are complete or an explicit limitation is recorded;
- at least 20 recording/camera groups and all recording/shot/court/venue contribution caps pass;
- orientation follows this convention; unresolved cases remain unresolved and cannot be accepted by the evaluator;
- all records have distinct annotator/reviewer IDs and completed review; required disagreements are adjudicated or final evidence remains explicitly uncertain;
- no point or line came from detector output, an automatic overlay, or a previous unreviewed calibration;
- no discernible difficult court disappeared as a silent negative or unexplained exclusion;
- the diversity matrix contains actual counts and explicitly names unavailable conditions;
- leakage diagnostics and a manual near-duplicate/group audit are complete;
- synthetic examples and process-QC duplicates are absent from real pilot statistics;
- the manifest, ledger, source list, annotation convention, evaluator version, and file hashes are frozen together before detector replay.

Failure of a gate means the dataset remains draft. “120 files exist” is never sufficient.

## Future baseline evaluation procedure

After separately authorized collection and review:

1. Freeze a versioned 120-frame manifest and ledger; record their SHA-256 hashes. Do not alter labels after viewing detector results. Corrections require a new dataset version and an audit note.
2. Validate schema, files, hashes, dimensions, unique content, grouping, review completion, diversity counts, and leakage findings.
3. Run the unchanged existing detector through the Phase 1 offline runner with its recorded committed defaults.
4. Evaluate every returned proposal with the independent point/court-coordinate/visible-line evaluator. Preserve detector `detected`, `low_confidence`, or `failed` separately from `accept`, `abstain`, or `incorrect` geometry evidence.
5. Report all three geometric outcomes, input failures, proposal confidence, corner/landmark projection errors, court-coordinate error, per-line alignment/support, and explicit reasons.
6. For current-detector `detected` proposals with scorable reviewed evidence, report accepted-geometry correctness as independently supported geometry divided by supported plus contradicted geometry. Also report detected proposals that abstain for insufficient evidence as unsupported acceptances; never count them as correct.
7. Report supported-view coverage as current-detector `detected` proposals that independently evaluate `accept`, divided by all adjudicated `full_geometry_supported` frames. Report acceptance over all 120 inputs separately.
8. Report raw frame counts and grouped results by recording, venue, court, camera setup, primary stratum, and condition tag where counts permit. Do not treat correlated frames as independent trials; state small or absent slices.
9. Publish exact-duplicate and cross-split leakage diagnostics plus manual near-duplicate/group findings. The pilot remains `development`; it is not a frozen model test set.
10. Review incorrect and unsupported-acceptance cases by failure mode without changing labels or detector thresholds. Record exclusions and input failures rather than dropping them.
11. Compare results with the proposed targets of at least 98% accepted-geometry correctness and at least 60% supported-view coverage. They remain unevaluated until this run. Passing either target on 120 pilot frames is limited pilot evidence, not population accuracy or production authorization.

## Existing 24 unique sampled images

The previously inventoried images are candidates only. Before any is selected, verify authorized dataset use and retention, source/artifact identity, source-video hash where possible, recording/venue/court/camera grouping, exact image hash, decoded dimensions, and whether it adds needed diversity within the contribution caps. Deduplicate versions and repeated fixtures.

An eligible image then follows the same blind annotation, independent review, adjudication, and completion gates as newly sourced material. Reject it when provenance, use eligibility, target identity, image integrity, or grouping is insufficient. Do not count it because it is already local, previously confirmed, or easy for the detector. No existing candidate is reviewed ground truth today.

## Preparation boundary

This protocol does not authorize collection, copying private media, annotation, detector replay on pilot candidates, training, model downloads, production integration, threshold changes, or deployment. The current reviewed-real count remains zero until a separately authorized collection task completes the review gates.
