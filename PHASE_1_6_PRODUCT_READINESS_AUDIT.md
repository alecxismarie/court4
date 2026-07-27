# Court4 Phase 1.6 Product Readiness Audit

Date: 2026-07-27

## Executive verdict

**Verdict: `MOSTLY_READY`.**

Court4 is architecturally ready to begin a narrow, internal Phase 1.6A Active Play
framework. It is **not** ready to publish Active Play intervals, replace current
analytics with active-play-only values, or claim that it can reliably distinguish
gameplay from every kind of non-gameplay.

The positive case is concrete:

- tracking persists frame indices, timestamps, detection confidence, court-space
  positions, inclusion flags, and raw track identity in
  `tracking/observations.jsonl` (`app/schemas/player_tracking.py:59-72`;
  `app/services/video/player_analysis.py:353-398`);
- candidate building preserves fragment lineage, observed spans, court movement,
  court side, quality reasons, and deterministic association evidence
  (`app/schemas/player_candidates.py:44-93`;
  `app/services/candidates/service.py:586-669`);
- movement analytics already refuse to add distance across raw-track changes or
  observation gaps longer than one second and expose observed time, gaps, and
  continuity warnings (`app/services/analytics/movement.py:323-377`);
- court zones and continuity-safe in-court time already exist
  (`app/services/analytics/zones.py:14-84`);
- recording/readiness assessment and Match IQ already use typed abstention and
  confidence gates (`app/services/recording_quality/assessment.py:19-40,167-381`;
  `app/services/match_iq/engine.py:425-515`); and
- calibration schema v2 already supports partial interval review, reviewer state,
  development/validation/holdout assignment, and non-mutating development-only
  threshold simulation (`app/schemas/evidence_calibration.py:33-42,74-77,296-337,
  381-440`; `app/services/evidence_calibration/evaluator.py:1174-1253`).

The limiting case is equally concrete:

- current analytics describe one selected player, not a reliable multi-player
  recording-level state (`app/services/analytics/movement.py:71-100`);
- no persisted per-window velocity, smoothing, acceleration, direction-change,
  stationary-period, or movement-intensity feature set exists;
- the field presented as `player_visibility_ratio` is currently the candidate's ratio
  of detected observations that fall inside the calibrated court, not the fraction of
  source frames in which the player was visible
  (`app/services/recording_quality/assessment.py:251-260`;
  `app/services/candidates/service.py:709-725`);
- the primary candidate selection policy excludes low-movement candidates
  (`app/services/candidates/service.py:972-988`), which is unsafe evidence selection
  for a live player standing at the kitchen or preparing to serve;
- real tracking remains generic-person YOLO/ByteTrack with unresolved spectators,
  duplicates, fragmentation, and no labeled identity ground truth
  (`REAL_VIDEO_RELIABILITY_REPORT.md`; `TRACK_CONTINUITY_REPORT.md`);
- the current two-video calibration set has no reviewed tracking intervals, no
  holdout, no `GOOD` or `EXCELLENT` sample, and no Active Play labels
  (`calibration/manifest.v2.json`; `calibration-results.json`); and
- movement alone cannot always distinguish warm-up, ball retrieval, side changes, or
  casual walking from gameplay. Those ambiguous cases must be calibrated and may need
  to remain `UNKNOWN`; they must not be converted into confident gameplay claims.

The smallest safe Phase 1.6A is therefore a deterministic, explainable, recording-level
interval artifact run in shadow mode. It should produce `LIKELY_ACTIVE`,
`LIKELY_IDLE`, or `UNKNOWN` from gap-aware multi-player movement evidence, without
changing current analytics, Match IQ, cards, or dashboards.

## Scope and product definition

For this audit, Active Play means a recording-level estimate of whether meaningful
gameplay is likely occurring. It does not identify rallies, points, serves, shots,
scores, tactics, causes, or outcomes.

That distinction matters. Court4 has motion and court-position evidence; it does not
have ball, paddle, shot, score, or point-boundary evidence. Phase 1.6A can therefore
measure **activity likelihood**, subject to explicit uncertainty. It cannot make an
unqualified claim that every active-looking interval is competitive play.

This audit does not propose Active Play Detection implementation, ball tracking, shot
recognition, rally scoring, coaching, LLMs, Player History, or deployment work.

## 1. Current signal availability

Status meanings:

- `AVAILABLE`: currently persisted or directly computed by a production service.
- `DERIVABLE`: existing persisted data is sufficient, but no current production field
  or service computes the signal.
- `PARTIAL`: some related evidence exists, but its semantics, coverage, or reliability
  are insufficient for direct Active Play use.
- `MISSING`: the required signal and an adequate derivation are absent.
- `UNRELIABLE`: an apparent signal exists, but current real-video evidence makes it
  unsafe to treat as the stated fact.

| Signal | Status | Evidence and product interpretation |
| --- | --- | --- |
| Player position over time | `AVAILABLE` | Every `PlayerObservation` includes `frame_index`, `timestamp_seconds`, `track_id`, image ground point, transformed `court_position`, and court inclusion flags (`app/schemas/player_tracking.py:59-72`). The tracker writes every detection to `observations.jsonl` (`app/services/video/player_analysis.py:353-398`). Selected-player in-court positions are also persisted in `timeline.json` (`app/schemas/analytics.py:8-25`; `app/services/analytics/movement.py:380-389`). Position accuracy still depends on bounding boxes and homography. |
| Timestamps | `AVAILABLE` | Timestamp is computed as `frame_index / source_fps` and persisted per observation (`app/services/video/player_analysis.py:319-326,353-370`). The tracking report also persists frame counts, interval, duration, and skipped frames (`app/schemas/player_tracking.py:105-136`). Default frame processing interval is one (`app/config/settings.py:47-57`). |
| Tracked and untracked intervals | `DERIVABLE` | Ordered observations plus source frame timing are enough to construct candidate-local observed and gap intervals. Current code calculates only aggregate observed and unobserved duration with a one-second continuity boundary (`app/services/analytics/movement.py:351-364`); explicit interval boundaries are not persisted. Identity ambiguity means intervals must be candidate-evidence intervals, not assumed ground-truth player presence. |
| Player velocity | `DERIVABLE` | Consecutive court positions and timestamps support gap-safe velocity. Current code persists only aggregate distance divided by observed duration (`app/services/analytics/movement.py:323-348`) and candidate movement rate (`app/services/candidates/service.py:720-725`). There is no per-window velocity artifact. |
| Smoothed velocity | `MISSING` | No smoothing filter, robust derivative, or smoothed velocity schema/service/test exists. Heatmap Gaussian blur is image rendering, not motion smoothing (`app/services/analytics/heatmap.py:16-44`). |
| Acceleration or speed change | `DERIVABLE` | It can be calculated from a new gap-safe velocity series because timestamps and positions exist. It is not currently calculated or persisted. Without smoothing and a minimum time delta, homography/bounding-box jitter would dominate. |
| Direction changes | `DERIVABLE` | Direction vectors can be calculated from the same ordered court-position series. No current schema or service does so. Changes across raw-track identity boundaries or long gaps must be forbidden, matching existing distance policy (`app/services/analytics/movement.py:330-339`). |
| Movement intensity | `PARTIAL` | Candidate-level court movement rate and selected-player average movement exist (`app/schemas/player_candidates.py:76-78`; `app/schemas/analytics.py:28-35`), but no time-local, smoothed, multi-player intensity definition exists. Treating current average speed as Active Play intensity would erase boundaries and create circular metrics. |
| Stationary periods | `DERIVABLE` | A duration-under-speed-threshold feature can be derived after smoothing. It is not implemented. Current candidate policy treats limited movement as a selection exclusion (`app/services/candidates/service.py:972-988`; `tests/test_player_candidates.py:165-186`), so it cannot be reused as a gameplay-idle rule. |
| Player visibility | `PARTIAL` | The tracker records detection confidence and missing observations are visible in the timestamp series. However, `player_visibility_ratio` is assigned from `in_court_observation_ratio`, which is `in_court detections / all detections`, not `visible source frames / expected source frames` (`app/services/recording_quality/assessment.py:251-260`; `app/services/candidates/service.py:709-725`). A true per-window presence/coverage feature is required. |
| Candidate continuity | `PARTIAL` | Candidate schema records raw fragments and merge evidence; deterministic association blocks overlap, opposite sides, implausible travel, size mismatch, and weak appearance re-entry (`app/schemas/player_candidates.py:44-93`; `app/services/candidates/service.py:608-688`). Tests cover simultaneous-person separation and unsafe merges (`tests/test_player_candidates.py:49-142`). Real-video grouping remains unvalidated and contains duplicates/ambiguous chains. |
| Tracking gaps | `AVAILABLE` | Aggregate `unobserved_gap_seconds`, gap ratio, fragment count, and warnings are persisted in current analytics/readiness (`app/schemas/analytics.py:63-100`; `app/schemas/recording_quality.py:46-59`). Existing analytics never interpolate gap distance (`app/services/analytics/movement.py:323-377`; `tests/test_movement_analytics.py:110-152`). Exact gap intervals are derivable but not an artifact today. |
| Court-zone occupancy | `AVAILABLE` | Kitchen, transition-zone, baseline-area seconds and percentages are computed only over continuity-safe same-track in-court intervals up to one second (`app/services/analytics/zones.py:14-84`). Current output is selected-player aggregate, not recording-level per-window occupancy. |
| Simultaneous movement across players | `PARTIAL` | Raw observations share frame indices/timestamps, so frame-aligned multi-person features are technically possible. Candidate association explicitly prevents simultaneous raw tracks from merging, with a deterministic test (`tests/test_player_candidates.py:49-84`). But no current service computes simultaneous movement, and candidate identity/spectator filtering is not reliable enough to call all aligned tracks players. |
| Number of reliably observed players | `UNRELIABLE` | `detected_people` is raw fragment count and selectable candidates are movement-filtered and capped at four (`app/services/candidates/service.py:198-211,991-1031`). The landscape artifact has 161 raw tracks and 80 legacy candidates for four expected players, with unresolved duplicates and spectators. This is not a reliable observed-player count. |
| Usable in-court observation time | `AVAILABLE` | `zone_occupancy.tracked_time_seconds` sums same-track, in-court intervals no longer than one second (`app/services/analytics/zones.py:37-79`). Current candidate/readiness `total_observed_duration` is less precise because it spans all detections within each fragment, not only in-court intervals (`app/services/candidates/service.py:720-725`). Active Play must use the former semantics or a stricter window equivalent. |
| Recording and tracking quality | `AVAILABLE` | Typed upload and analysis assessments expose status, checks, reason codes, guidance, candidate quality, observed duration, gaps, and fragments (`app/schemas/recording_quality.py`; `app/services/recording_quality/assessment.py`). Match IQ carries five confidence dimensions and abstention gates (`app/schemas/match_iq.py:8-31`; `app/services/match_iq/engine.py:425-515`). These are initial engineering categories, not calibrated probabilities (`RECORDING_STANDARD.md`; `INSIGHT_INTEGRITY_DESIGN.md`). |

### Signal conclusion

Court4 has enough raw temporal and court-space evidence to implement a feature extractor
without changing the detector. It does not yet have the interval feature contract or
multi-player reliability safeguards needed by a classifier. The most important
precondition is not another aggregate metric; it is an honest, per-window evidence
model that distinguishes:

1. observed low movement;
2. unobserved or uncertain time;
3. reliable multi-player movement; and
4. apparent motion from weak candidates, spectators, identity resets, or coordinate
   jitter.

## 2. Minimum viable Active Play model

### Recommended initial state model

Use three public/internal states for Phase 1.6A:

- `LIKELY_ACTIVE`
- `LIKELY_IDLE`
- `UNKNOWN`

Do **not** use authoritative `ACTIVE` or `IDLE` yet. The proposed five-state model
(`ACTIVE`, `LIKELY_ACTIVE`, `LIKELY_IDLE`, `IDLE`, `UNKNOWN`) suggests two levels of
certainty that the current uncalibrated data cannot support. A three-state model keeps
uncertainty explicit and avoids disguising engineering thresholds as probabilities.

Each interval should additionally carry:

- categorical evidence confidence: `HIGH`, `MODERATE`, `LOW`, or `NOT_AVAILABLE`;
- policy version;
- reason codes;
- feature-window lineage;
- observed-player-evidence count and coverage;
- recording/readiness gate;
- boundary source and boundary uncertainty; and
- limitations.

State and confidence must remain separate. For example, an interval can be
`LIKELY_ACTIVE` with `LOW` confidence rather than silently becoming `UNKNOWN` for every
warning, while hard evidence failures must force `UNKNOWN`.

### Minimum inputs and rules

| State | Minimum required inputs | Required behavior |
| --- | --- | --- |
| `UNKNOWN` | Any blocking recording/readiness failure; inadequate calibrated in-court observations; tracking gap/occlusion beyond policy; fewer than the minimum reliable candidate-evidence streams; conflicting identity evidence; insufficient clip context | `UNKNOWN` overrides movement. Missing detections must never become idle. Persist exact reasons such as `tracking_gap`, `insufficient_player_coverage`, `recording_unsuitable`, or `boundary_uncertain`. |
| `LIKELY_ACTIVE` | Valid calibration; acceptable recording/readiness; sufficient per-window observed coverage; gap-safe smoothed movement features; multiple candidate-evidence streams where format allows; temporal support before/after the window | Require more than one raw movement spike. Use windowed aggregate speed/intensity, count of independently moving candidate streams, direction-change evidence, in-court occupancy, and entry/exit context. Hysteresis should preserve brief low-motion phases such as serve preparation or kitchen waiting. |
| `LIKELY_IDLE` | Same observation-quality minimum as `LIKELY_ACTIVE`; sustained low coordinated movement or a reviewed non-play pattern; no gap/occlusion ambiguity | Require positive evidence of sustained observed inactivity, not absence of detections. Use minimum dwell time and transition hysteresis. Walking, retrieval, side switching, and warm-up patterns must not be assumed idle merely because one feature is low. |

The model should operate on fixed, overlapping evidence windows and then consolidate
windows into intervals with deterministic hysteresis. Policy values must be centralized
and versioned. Phase 1.6A should not attach rally, point, serve, or score semantics.

### Honest product claim

The first version can claim:

> Court4 identifies intervals that are likely active, likely idle, or too uncertain to
> classify from observed player movement and tracking quality.

It cannot yet claim:

> Court4 knows exactly when every rally or point starts and ends.

## 3. Architectural fit

### Recommended pipeline position

Active Play should be a recording-level derived-evidence stage after candidate
construction and analysis-readiness assessment, but before any active-play-only
selected-player analytics:

```text
inspection -> court calibration -> raw tracking observations
           -> candidate association/review + recording readiness
           -> Active Play window evidence and intervals
           -> optional active-play-only selected-player analytics
           -> Match IQ / cards / dashboard only after validation
```

The clean integration point is a new `app/services/active_play/` service consuming:

- raw `PlayerObservation` rows as the authoritative time/position source;
- candidate lineage and association evidence as a grouping aid;
- all plausible in-court candidate streams, including low-movement candidates;
- court-zone classification;
- upload preflight and analysis readiness;
- explicit gap, coverage, and confidence gates; and
- an immutable, versioned Active Play policy.

It should **not** consume only the currently selected player. Active Play is a property
of the recording interval, and a player may be stationary during live play.

It should **not** consume only `collection.candidates`. That collection is deliberately
selection-oriented: low-movement candidates can be excluded and active candidates are
capped at four (`app/services/candidates/service.py:972-1031`). Phase 1.6A needs an
Active-Play-specific projection over candidate and raw-track evidence that can retain
stationary on-court people without promoting every spectator.

It should **not** derive states from current aggregate analytics. Total distance,
average movement, and whole-recording zone percentages have already discarded the
temporal boundary information Active Play needs.

### Proposed artifact boundary

Use a new recording-level artifact namespace rather than hiding Active Play inside the
selected-player timeline:

- `active_play/active_play.json` — report, policy version, summary, intervals,
  coverage, confidence, limitations, source artifact references;
- `active_play/windows.jsonl` — optional deterministic window evidence for calibration
  and debugging;
- no annotated video in the minimum milestone; and
- no mutation of `tracking/observations.jsonl`.

`active_play.json` should be reproducible from source artifacts and policy. It should
record the candidate schema/version or digest and recording/readiness assessment used.

### Systems that do not need to change

If Phase 1.6 started tomorrow, these parts of Court4 would not need a fundamental
change:

- video upload, validation, metadata extraction, sampled frames, and artifact
  retrieval;
- automatic/manual court calibration, homography, pickleball geometry, and current zone
  boundaries;
- controlled tracking backend and Ultralytics/ByteTrack adapter;
- raw observation persistence, bounding boxes, confidence, frame index, timestamp,
  ground point, and court position;
- candidate ID/fragment lineage, deterministic association evidence, manual review,
  selection, merge, reject, restore, and undo workflows;
- recording-quality status/check/guidance contract;
- Match IQ's evidence/limitations/confidence/abstention architecture;
- calibration manifest loading, strict validation, partial-label preservation,
  artifact compatibility reporting, split handling, disagreement reporting, and safe
  threshold-simulation pattern;
- existing whole-recording analytics fields and artifacts;
- current heatmap/trajectory renderers for whole-recording views; and
- current share-card renderer and dashboard aggregation during Phase 1.6A.

Some of these systems will gain additive references or optional consumers, but their
current responsibilities should stay unchanged.

### Systems that do need additive work

- new Active Play schemas, policy, feature extractor, state engine, persistence, and
  focused API;
- a coverage/presence definition based on expected processed frames or time windows,
  not in-court-detection ratio;
- an Active-Play-specific candidate evidence projection that does not exclude
  stationary players;
- explicit interval and window outputs;
- Active Play calibration labels, boundary review, false-active/false-idle metrics, and
  policy simulation;
- optional analytics dual-scope fields only after interval validation; and
- a new Active Play confidence dimension if downstream Match IQ eventually consumes
  the result.

## 4. Downstream product value

Court4 should preserve both:

1. **whole-recording / observed-tracking metrics**, retaining today's meaning and
   backward compatibility; and
2. **active-play-only metrics**, added later with an explicit scope, active duration,
   unknown duration, coverage, policy version, and confidence.

Never silently replace a persisted whole-recording value with an active-play-only
value. That would make old and new analyses incomparable and would hide classifier
errors.

| Metric or feature | Expected effect | Product guidance |
| --- | --- | --- |
| Distance | Material improvement | Active-only distance can remove walking, retrieval, and setup motion, making gameplay workload more relevant. Preserve current continuity-safe observed distance as `WHOLE_RECORDING`; add active-only distance only after validation. False-idle intervals will undercount distance. |
| Speed | Material improvement, high bias risk | Active-only average speed is more gameplay-specific, but using movement to select active windows and then reporting speed creates selection bias. Report denominator and scope; preserve current average. |
| Heatmaps | Material improvement | Active-only heatmaps can better represent gameplay positioning instead of setup, retrieval, or side changes. Keep the whole-recording heatmap available and label both. |
| Court coverage | Material improvement, but not currently first-class | Court4 currently exposes average court position, heatmap, trajectory, and zone occupancy rather than a dedicated court-coverage metric. Any future coverage metric should be dual-scope and confidence-aware. |
| Kitchen time | Material improvement | Active-only kitchen time is more meaningful for gameplay positioning. Slow kitchen exchanges make false-idle especially harmful. |
| Transition-zone time | Material improvement | Removes transition occupancy caused by non-play walking, but side changes and retrieval are hard negatives that require labels. |
| Baseline time | Material improvement | Removes serve setup, waiting, and camera setup only if boundaries are correct. Serve preparation must be bridged into likely active context rather than automatically discarded. |
| Movement intensity | Material improvement to relevance; misleading if circular | No current first-class intensity metric exists. Define raw window intensity independently, then distinguish the feature used by the detector from the player-facing active-only summary. |
| Match IQ | Material improvement after validation; highly misleading if poor | Better temporal scope could improve relevance of movement/zone observations. A bad classifier would make deterministic statements confidently wrong. Phase 1.6A should not change Match IQ; later use the existing evidence gate and add Active Play confidence/coverage. |
| Recording-quality output | Slight improvement as a separate diagnostic | Active Play can add `classifiable_time`, `unknown_time`, and active-observation coverage. It must not rewrite source recording quality, which measures a different layer. |
| Confidence | Material improvement | Add Active Play confidence and limitation reasons; do not merge it into tracking confidence. The weakest relevant layer should continue to win. |
| Shareable performance cards | Material improvement only after validation; severe misuse risk | Active-only metrics are more compelling but more likely to be misunderstood. No card changes in Phase 1.6A. Later cards must display scope and active duration and suppress results with low coverage/high unknown time. |
| Dashboard summaries | Material improvement only with migration-safe scopes | Current dashboard sums completed-analysis distance and tracked time (`web/lib/workspace-data.ts:32-43`). Preserve those totals. Add separate active-play totals only when comparable policy versions and sufficient coverage exist. |

## 5. Failure modes

For the final column, “blocks Phase 1.6A” means blocks the proposed internal,
shadow-mode framework unless the stated safeguard is part of its design. Some cases do
not block framework construction but do block a player-facing Active Play claim.

| Failure mode | Likely cause | Current protection | Required mitigation | Blocks Phase 1.6A? |
| --- | --- | --- | --- | --- |
| Slow dink exchanges classified idle | Low player displacement; motion thresholds dominate; one or more players wait at the kitchen | None specific. Court zones exist; candidate selection can penalize low movement. | Multi-player windows, lower-speed evidence, direction-change features, temporal bridging/hysteresis, labeled slow-dink examples, and `UNKNOWN` when evidence is insufficient. | No for shadow mode; blocks product release until measured. |
| Serve preparation classified idle | Server and receiver may be stationary before a live serve; no serve/ball evidence | None. | Pre/post movement context, configurable lead-in/bridge time, multi-player formation stability, and boundary-tolerance labels. Do not claim serve recognition. | No, with explicit boundary uncertainty. |
| Players waiting at the kitchen during a live rally | A selected player can be stationary while another participant moves | Raw simultaneous observations exist, but no multi-player movement service; stationary candidates can be selection-ineligible. | Recording-level aggregation across plausible players; retain stationary on-court evidence; require independent movement/coverage support rather than selected-player speed. | Yes if the engine uses only selected/eligible moving candidates. |
| Casual walking after a point classified active | Movement magnitude resembles play | No Active Play protection. | Sustained multi-player coordination, formation/zone-transition context, hysteresis, hard-negative labels, and conservative `UNKNOWN` near boundaries. | No for shadow mode; blocks release if false-active rate is high. |
| Ball retrieval classified active | One player moves quickly, sometimes on court, while others wait or disappear | Court inclusion flags and zones only. | Minimum reliable-player coverage, one-mover-versus-group features, out-of-court transitions, contextual dwell, retrieval labels, and uncertainty. Without ball evidence, some cases remain irreducible. | No for shadow mode; must be a named validation cohort. |
| Warm-up classified active play | Warm-up can be visually and kinematically indistinguishable from gameplay without ball/shot/score context | None. Recording standard explicitly says Court4 does not recognize gameplay/rallies. | Include warm-up hard negatives; allow user/session trimming or recording metadata later; keep ambiguous intervals `UNKNOWN`; phrase output as likelihood from movement evidence. | No for shadow framework; **yes** for an unqualified “gameplay detected” claim. |
| Side switches classified active | Multiple players walk across the court together | Court side is available only as a candidate aggregate. | Detect coordinated net crossing/formation reset, require post-transition activity support, and label side-switch intervals. | No, if included in calibration. |
| Fragmented tracking classified inactivity | Missing candidate observations look like zero movement | Existing analytics expose gaps and do not bridge distance. | Hard rule: missing/gap windows become `UNKNOWN`, never `LIKELY_IDLE`; preserve gap reasons and coverage. | **Yes** until this invariant is tested. |
| Occlusion classified inactivity | Detector miss during active play | Calibration schema can label occlusion; current dataset has no interval labels. | `UNKNOWN` override for coverage loss, gap-aware windowing, optional short-gap bridging only as uncertain evidence, occlusion cohort labels. | **Yes** until this invariant is tested. |
| One visible player moving while others are untracked | Narrow framing, occlusion, detector miss, or spectator confusion | Recording/readiness gates are aggregate and selected-player oriented. | Minimum independent candidate-evidence coverage by format; low confidence or `UNKNOWN`; never infer full-play state from one weak stream by default. | **Yes** as a default-policy safeguard. |
| Vertical or distant footage | Partial court, small players, homography error, missed far-side tracks | Vertical/resolution warnings and `LIMITED`/`UNSUITABLE` gates exist. Real vertical sample is `LIMITED`; distant coverage is not reviewed. | Active Play quality gate using court coverage, candidate coverage, subject size, unknown ratio, and cohort validation. `UNSUITABLE` must force `UNKNOWN`. | **Yes** until quality gating is wired. |
| Short clips | Too little pre/post context and unstable rates | Upload duration under 10 seconds is blocking; Match IQ has minimum observations/time. | Separate Active Play minimum classifiable duration and boundary context; return `UNKNOWN` or insufficient evidence rather than extrapolating. | **Yes** until minimum-context policy exists. |
| Long dead-time recordings | Whole-recording metrics become dominated by waiting/setup; a major intended use case | Current analytics honestly report observed tracking but do not separate play. | Efficient window processing, long-idle labels, active/idle/unknown duration summaries, and preservation of both metric scopes. | No; this is a primary value case. |

## 6. Data and calibration readiness

### What the current framework supports

| Capability | Current status | Evidence |
| --- | --- | --- |
| Interval-based labels | `PARTIAL` | `TrackingReviewInterval` supports start/end, expected player, candidate, identity, continuity, occlusion, outside-frame, gap, observed-time agreement, uncertainty, and notes (`app/schemas/evidence_calibration.py:296-315`). It has no Active Play state label. |
| Partial review | `AVAILABLE` | `ReviewStatus` distinguishes not reviewed, partially reviewed, and reviewed; sections and labels are optional (`app/schemas/evidence_calibration.py:33-42,374-409`). |
| Active/idle boundary review | `MISSING` | Time ranges exist, but there is no activity boundary type, tolerance, precision, neighboring state, or boundary error metric. |
| Confidence review | `PARTIAL` | Sample/stage reviewer confidence exists, and tracking intervals have `uncertain_interval`; there is no per-Active-Play-interval state confidence or reviewer-confidence field. |
| False-active and false-idle metrics | `MISSING` | Current evaluator covers recording, gates, candidate mapping, tracking continuity, and insight review, not Active Play confusion by interval duration or boundary. |
| Development/validation/holdout splits | `AVAILABLE` | Schema and evaluator enforce the split; validation and holdout are excluded from threshold simulation (`app/schemas/evidence_calibration.py:74-77,381-440`; `tests/test_evidence_calibration_dataset.py:272-310`). |
| Threshold simulation without production mutation | `PARTIAL` | The pattern is implemented and tested for `RecordingQualityThresholds`; it is development-only and immutable (`app/services/evidence_calibration/evaluator.py:1174-1253`). Active Play needs a separate policy/simulator and metrics. |

### Required schema additions

Add an optional Active Play review section rather than overloading tracking identity
review:

- `ActivePlayLabel`: `ACTIVE_PLAY`, `NON_PLAY`, `UNCERTAIN`, `NOT_REVIEWED`;
- `NonPlayReason`: `WAITING`, `TALKING`, `WARM_UP`, `BALL_RETRIEVAL`,
  `CHANGE_SIDES`, `BETWEEN_POINTS`, `CAMERA_SETUP`, `OTHER`, `UNKNOWN`;
- `ActivePlayReviewInterval`:
  - start/end time;
  - label;
  - optional non-play reason;
  - boundary precision/tolerance;
  - reviewer confidence;
  - partial-review flag;
  - visibility/occlusion caveat;
  - notes;
- `ActivePlayReview`:
  - reviewed coverage ranges;
  - intervals;
  - reviewer/adjudication metadata;
  - whether warm-up and setup are present;
- active-play policy simulations in a separate versioned policy family;
- evaluation metrics:
  - false-active duration / reviewed non-play duration;
  - false-idle duration / reviewed active-play duration;
  - unknown duration by reviewed class;
  - classifiable coverage;
  - interval overlap/IoU;
  - start/end boundary error within a declared tolerance;
  - metrics by failure-mode cohort and recording-quality cohort; and
  - raw counts/durations with provisional status.

Do not force complete-video annotation. The v2 partial-review design is appropriate:
only reviewed coverage belongs in denominators, and unlabeled time remains excluded.

### Readiness separation

**Implementation readiness: `MOSTLY_READY`.** The persisted observations, candidate
lineage, zone geometry, evidence gates, workflow, and deterministic calibration
infrastructure are adequate. The missing feature/state schemas and safeguards are a
bounded addition.

**Calibration readiness: `PARTIAL`.** The framework can accept additive interval
labels and safe splits, but Active Play labels, boundary review, metrics, and policy
simulation do not exist.

**Validation readiness: `NOT_READY`.** The current manifest contains two partially
reviewed indoor recordings: one development and one validation sample, no holdout, no
reviewed tracking intervals, no `GOOD`/`EXCELLENT` samples, and no Active Play labels.
`calibration-results.json` explicitly reports a two-sample dataset, zero reviewed
tracking intervals, and unmeasured generalization.

The two seed videos are useful regression cases, not a calibration set.

### Data collection required in parallel

Extend the existing 20–30 recording target rather than create a separate ad hoc set.
Collect and independently review:

- `GOOD` and `EXCELLENT` landscape recordings, plus `LIMITED` and `UNSUITABLE`
  negatives;
- singles and doubles; indoor and outdoor; baseline and diagonal; near and distant;
- full-match-like long recordings and short clips;
- explicit waiting, talking, camera setup, warm-up, retrieval, side-switch, and
  between-point intervals;
- slow dinks, serve preparation, kitchen waiting during live play, and low-movement
  rallies;
- occlusion, fragmentation, one-player-visible, and partial-court intervals;
- stable identity mappings for a gold subset;
- development, validation, and untouched holdout assignments made before tuning; and
- two reviewers plus adjudication on a smaller boundary-focused gold subset.

At least the critical failure-mode cohorts must have multiple reviewed examples; a
single interval must never determine a threshold.

## 7. Minimum Phase 1.6A implementation scope

Phase 1.6A should create a measurable framework, not a player-facing feature.

### New schemas

- `ActivePlayState`: `LIKELY_ACTIVE`, `LIKELY_IDLE`, `UNKNOWN`;
- `ActivePlayConfidence` and reason-coded evidence gate;
- `ActivePlayWindowEvidence` with window times, observed coverage, plausible candidate
  count, independently moving count, raw/smoothed speed summaries, direction-change
  summary, zone occupancy, gap/occlusion flags, and reasons;
- `ActivePlayInterval` with state, confidence, boundaries, window lineage, reasons, and
  limitations;
- `ActivePlayReport` with schema/policy version, source artifact references/digests,
  interval/duration summaries, unknown coverage, quality gate, and artifacts;
- additive calibration review and metric schemas described above.

### Services and policy

- `app/services/active_play/features.py`: deterministic, gap-safe, frame/window-aligned
  feature extraction over raw observations and candidate evidence;
- `app/services/active_play/engine.py`: three-state rules plus hysteresis;
- `app/services/active_play/persistence.py`: stable JSON/JSONL output and loading;
- `app/services/active_play/policy.py`: immutable centralized thresholds and policy
  version;
- explicit quality gate that forces `UNKNOWN` for unobserved/unsuitable windows;
- no cross-fragment derivatives or interpolation;
- no dependency on player selection; and
- no model, LLM, ball, shot, score, or rally inference.

### Artifact outputs

- `active_play/active_play.json`;
- optional `active_play/windows.jsonl` for review and simulation;
- generated calibration report sections and disagreement entries;
- no new video rendering in 1.6A.

### API changes

Add a typed internal endpoint or workflow action to generate/read the artifact:

- `POST /api/v1/analyses/{analysis_id}/active-play`
- `GET /api/v1/analyses/{analysis_id}/active-play`

Generation should require completed tracking/candidates and should be idempotent for the
same source digest and policy version. It should not require selected-player analytics.

### Analytics integration

In Phase 1.6A:

- preserve existing `analytics.json`, `movement_summary.json`, `timeline.json`,
  heatmap, trajectory, Match IQ, share cards, and dashboard semantics;
- optionally expose only an additive artifact reference and classifiable/unknown
  duration to internal diagnostics;
- calculate candidate active-only metrics for offline comparison only if clearly marked
  experimental and not returned to player-facing UI; and
- defer replacement/addition of player-facing active-only metrics to a later validated
  phase.

### UI changes

No player-facing Active Play UI is required. If inspection is necessary, use a minimal
development-only interval/evidence view or calibration report. Do not add Active Play
badges, timelines, cards, dashboard totals, or Match IQ claims in 1.6A.

### Calibration labels

- additive activity intervals and non-play reasons;
- partial reviewed coverage;
- uncertain boundaries and tolerance;
- reviewer confidence and adjudication;
- false-active, false-idle, unknown, coverage, overlap, and boundary metrics;
- fixed splits and development-only policy simulation.

### Focused tests

- timestamp/window alignment at multiple FPS and frame intervals;
- derivatives never cross raw-track changes or gaps;
- missing/occluded windows become `UNKNOWN`, never idle;
- stationary on-court candidates remain available to Active Play evidence;
- simultaneous distinct people remain distinct;
- slow-play and serve-preparation hysteresis fixtures;
- walking/retrieval/warm-up/side-switch hard-negative fixtures;
- vertical/distant/short-clip quality gates;
- deterministic artifact equality for a fixed time/policy/source;
- policy version/source digest invalidation;
- interval consolidation and boundary behavior;
- schema validation and backward-readable absent artifacts;
- partial label denominators;
- development-only simulations with validation/holdout exclusion;
- no mutation of production policy;
- false-active/false-idle/unknown metrics; and
- current movement analytics, Match IQ, API, cards, and dashboard regressions unchanged.

### Explicitly excluded

Ball tracking, shot recognition, rally/point segmentation, scoring, tactical analysis,
coaching, LLMs, Player History, deployment, and broad tracking refactors remain out of
scope.

## 8. Go/no-go criteria

### Verdict definitions

#### `READY`

Use only when:

- all required per-window features are currently available and semantically correct;
- presence/coverage is a true time-based signal;
- multi-player evidence does not depend on movement-filtered selected candidates;
- gap/occlusion/quality always gates to `UNKNOWN`;
- Active Play interval labels and false-active/false-idle metrics exist;
- calibration includes development, validation, and holdout coverage; and
- current evidence supports beginning the state engine without prerequisite schema or
  safeguard work.

Court4 does not meet this definition.

#### `MOSTLY_READY`

Use when:

- raw temporal/court evidence and architectural boundaries are sound;
- a deterministic service can be added without changing detector, calibration, or
  current analytics foundations;
- missing work is bounded to temporal features, evidence selection, state/policy
  schemas, uncertainty safeguards, and calibration additions; and
- implementation can begin in shadow mode while validation data is collected.

Court4 meets this definition.

#### `NOT_READY`

Use when:

- source observations lack timestamps or court-space positions;
- gaps cannot be distinguished from inactivity;
- track identity is irrecoverably discarded before temporal analysis;
- calibration/evidence architecture cannot represent uncertainty; or
- producing an interval framework would require replacing the tracker or current
  pipeline foundations.

Court4 does not meet this definition because its raw observations and evidence model
preserve the necessary foundation.

### Phase 1.6A acceptance gate

Phase 1.6A is complete only when:

1. fixed source artifacts plus a fixed policy produce deterministic interval/window
   artifacts;
2. no derivative or movement distance crosses a raw-track change or disallowed gap;
3. all tracking gaps, occlusions, blocking quality, and inadequate-player-coverage
   windows become `UNKNOWN`, never `LIKELY_IDLE`;
4. the engine uses recording-level candidate evidence and can retain stationary
   on-court participants;
5. every interval has reason codes, evidence lineage, policy version, confidence, and
   coverage;
6. calibration supports partial Active Play intervals, boundary uncertainty,
   false-active/false-idle/unknown metrics, and immutable development-only simulation;
7. validation and holdout samples cannot change policy;
8. current whole-recording analytics and player-facing outputs are byte/schema
   compatible except for explicitly optional additive references;
9. focused fixtures cover every failure mode in this audit; and
10. the implementation remains shadow-only, with no Match IQ, card, or dashboard
    promotion.

### Later product-release gate

Before player-facing active-only metrics:

- collect the planned balanced 20–30 recordings with a holdout and reviewed Active Play
  coverage;
- pre-register acceptance thresholds before opening the holdout;
- as an initial engineering proposal, require duration-weighted false-active and
  false-idle rates no greater than 10% overall on validation and holdout, no critical
  cohort greater than 15%, and zero cases where a known gap/occlusion is emitted as
  idle;
- require at least 80% classifiable coverage on reviewed `GOOD`/`EXCELLENT` recordings
  without using `UNKNOWN` to hide errors;
- report boundary error with a declared tolerance (initial proposal: median at most
  1.5 seconds and 90th percentile at most 3 seconds);
- review errors by warm-up, retrieval, side-switch, slow-play, serve-preparation,
  occlusion, vertical, distant, and short-clip cohorts; and
- require explicit product review before any metric, Match IQ, share-card, or dashboard
  semantic change.

These are proposed launch gates, not claims achieved by the current dataset.

## 9. Required final answers

### 1. Is Court4 ready to become an Active Play platform?

**Yes, at the architectural-foundation level. No, at the user-facing accuracy level.**
Court4 can begin a narrow interval-evidence framework now, but it cannot yet ship or
market reliable Active Play classification.

### 2. What is the verdict?

**`MOSTLY_READY`.**

### 3. What evidence supports that verdict?

- timestamped, court-space raw observations exist for every detection;
- source frame cadence and tracking performance are persisted;
- candidate lineage and deterministic association evidence exist;
- distance/zone analytics already honor gaps and raw-track boundaries;
- recording/readiness and Match IQ already support abstention, limitations, and
  separate confidence dimensions;
- calibration already supports partial interval review, fixed splits, artifact
  compatibility, disagreements, and safe development-only simulation; and
- focused tests cover simultaneous-person separation, fragment association, no
  cross-fragment movement, gap reporting, quality gates, partial reviews, and holdout
  exclusion.

### 4. What is missing?

- a per-window temporal feature contract;
- smoothed speed and gap-safe derived motion features;
- explicit observed/unobserved interval artifacts;
- true time-based player presence/coverage;
- reliable recording-level multi-player evidence selection;
- an Active Play state/policy/report schema;
- Active Play interval/boundary labels and metrics;
- balanced validation/holdout data; and
- evidence that warm-up, retrieval, walking, slow play, and occlusion errors are within
  acceptable limits.

### 5. What must be completed before implementation?

Before coding the state transitions, define and test:

1. Active Play state semantics and the `UNKNOWN` precedence rules;
2. true time-window coverage/presence semantics;
3. an Active-Play-specific candidate evidence projection that includes stationary
   on-court participants;
4. gap-safe smoothing/derivative boundaries; and
5. additive calibration labels and false-active/false-idle metrics.

These are bounded Phase 1.6A prerequisites, not reasons to redesign the tracker.

### 6. What should remain unchanged?

Upload/inspection, court calibration and geometry, tracking backends, raw observation
contract, candidate review workflow, whole-recording analytics, existing Match IQ
integrity gates, current player-facing UI, share cards, dashboard summaries, and the
calibration framework's split/mutation safety should remain unchanged in Phase 1.6A.

### 7. What is the smallest safe Phase 1.6A milestone?

A deterministic shadow-mode service that writes recording-level
`LIKELY_ACTIVE`/`LIKELY_IDLE`/`UNKNOWN` windows and intervals with coverage, confidence,
reason codes, source lineage, and policy version; plus Active Play labels and evaluation
metrics. It must not change player-facing analytics.

### 8. What are the top five product risks?

1. **Semantic ambiguity:** movement-only evidence cannot always separate gameplay from
   warm-up, retrieval, side changes, or casual walking.
2. **Stationary-live-play bias:** slow dinks, serve preparation, and a player waiting at
   the kitchen can look idle; current selection policy also excludes low movement.
3. **Identity and population error:** fragmentation, duplicates, spectators, and a
   capped/movement-filtered candidate list can corrupt multi-player evidence.
4. **Missing-evidence error:** occlusion, vertical/distant framing, and one-player
   visibility can be mislabeled as inactivity unless `UNKNOWN` strictly wins.
5. **Silent metric redefinition:** replacing whole-recording values with active-only
   values would make dashboards/cards misleading and historical analyses incomparable.

### 9. What data must be collected in parallel?

A balanced 20–30 recording set with development/validation/holdout splits and partial
interval labels covering active play, each named non-play reason, slow/low-motion live
play, serve preparation, occlusion/gaps, one-player visibility, vertical/distant
footage, short clips, and long dead-time recordings. A gold subset needs stable player
identity, two reviewers, boundary confidence, and adjudication.

### 10. Should implementation begin now?

**Yes, but only as the narrow Phase 1.6A shadow framework described here.** Data
collection and label-schema work should start in parallel. Do not enable active-only
product metrics or claims until the validation gate is met.

## 10. Validation performed for this audit

The audit used repository and artifact inspection only; no inference or unrelated
refactoring was performed.

Inspected:

- requested Phase 1.4–1.5A design, audit, reliability, recording, and continuity
  documents;
- tracking, candidate, analytics, quality, Match IQ, workflow, API, and calibration
  schemas/services;
- current tracking, candidate, movement, quality, Match IQ, and calibration tests;
- current two-sample v2 manifest and generated calibration results;
- preserved landscape and vertical tracking/candidate artifacts; and
- the preserved landscape analytics/timeline artifact.

Artifact checks confirmed:

- landscape real-video tracking persists 1,836 processed frames and 161 raw tracks;
- its legacy candidate artifact contains 80 candidates and no selected candidate;
- vertical tracking persists 432 processed frames, two raw tracks, and two legacy
  candidates;
- both candidate artifacts are schema 1 while current candidate schema is 3;
- the preserved landscape timeline contains 361 selected-track positions from 27.2 to
  40.233 seconds and 13.033 seconds of zone-tracked time;
- older analytics do not contain current observed-duration/gap/fragment fields, which
  reinforces the need for versioned Active Play artifacts and conservative legacy
  handling; and
- the first landscape observation row contains frame, timestamp, track, bounding box,
  confidence, ground point, court position, inclusion flags, and `interpolated: false`.

Focused validation used the existing local `court4:phase15a` image with the workspace
mounted read/write and no network or inference command:

```powershell
docker run --rm -v "${PWD}:/app" -w /app court4:phase15a sh -c `
  "python -m pytest -q tests/test_player_tracking.py tests/test_player_candidates.py tests/test_movement_analytics.py tests/test_recording_quality.py tests/test_match_iq.py tests/test_evidence_calibration_dataset.py && `
   python -m scripts.calibrate_evidence validate calibration/manifest.v2.json && `
   python -m scripts.calibrate_evidence summarize calibration/manifest.v2.json"
```

Results:

- all focused tracking, candidate, movement, recording-quality, Match IQ, and
  calibration-dataset tests passed;
- manifest v2 validated with two samples and schema 2;
- balance summary confirmed one development sample, one validation sample, no holdout,
  no `GOOD`/`EXCELLENT` samples, and the documented 20–30 recording recommendation;
  and
- no production artifact, label, policy, or threshold was changed.

## Final recommendation

Approve Phase 1.6A as an **evidence and calibration milestone**, not as a feature launch.
Build the interval feature contract and uncertainty invariants first, collect labels in
parallel, and preserve every existing whole-recording output. The correct next product
step is to prove that Court4 can abstain and bound error at activity boundaries before
it uses Active Play to make any metric look more intelligent.
