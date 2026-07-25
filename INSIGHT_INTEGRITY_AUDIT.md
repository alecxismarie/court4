# Court4 Insight Integrity Audit

**Audit date:** 2026-07-24
**Scope:** Current repository implementation only. No feature work was performed.
**Product standard:** “Provide understandable, honest, evidence-backed feedback that helps players improve.”

## Executive Summary

Court4 currently has a deterministic, traceable movement-measurement pipeline. It can
select a user-confirmed person candidate, map detected person locations to court
coordinates, calculate observed distance and zone occupancy, and attach rule thresholds
and source metrics to Match IQ statements. It also explicitly says that it does not
measure shots, rallies, the ball, opponents, scoring, or intent. Those are meaningful
foundations for honest feedback.

The present output is not yet a dependable improvement product, however. Match IQ mostly
relabels movement measurements; it does not explain whether a result is good or bad, why
it matters in the player's actual points, or what the player can safely practice.
More importantly, the engine does not carry tracking, candidate, calibration,
measurement, interpretation, or recommendation confidence into its decisions or UI.
Three observations and one second of tracked time are treated as enough for a “reliable
Match IQ,” without empirical support for those gates.

The strongest integrity defect is in the two timeline-half rules. Main distance analytics
correctly avoid cross-fragment and greater-than-one-second jumps, but the persisted
timeline removes track/fragment identity. Match IQ then recomputes half distances by
connecting adjacent timeline points, so an unobserved fragment change can be counted as
movement. Those two insights should be suppressed until they use continuity-safe
segments.

The real-video reports reinforce the confidence problem: they document generic person
detection, track fragmentation, spectator/duplicate risk, limited camera coverage, and
no labeled precision/recall evaluation. Current code improves the candidate review set by
requiring in-court movement and limiting active choices to four, but it still detects the
`person` class only. It does not detect paddles, prove that a person is playing, or
validate candidate identity automatically.

**Overall finding:** Court4 is in the **Honest Movement Summaries** phase, but the phase is
not complete. It has measurement provenance and cautious boundaries, while confidence,
sample adequacy, user-facing limitations, and safe action guidance remain incomplete.

## Current Insight Pipeline

### End-to-end trace

| Stage | What is directly measured or recorded | What is inferred or derived | What is assumed | What reaches the player |
| --- | --- | --- | --- | --- |
| Video and inspection | File bytes, frame dimensions, frame count/rate, duration, and sampled images | Whether the recording is processable and its orientation/suitability | Sampled frames represent the relevant recording conditions | Upload/inspection status and recording guidance |
| Court calibration | Four image points, either detected or manually clicked | A court quadrilateral and homography to a regulation 20-by-44-foot court | The chosen quadrilateral is the court boundary; the court is sufficiently planar; severe lens distortion is negligible | Automatic court-detection status/confidence during workflow; calibration ID later appears only in technical details |
| Person tracking | YOLO person boxes, detector score, ByteTrack IDs, frame/time, and box bottom-center | Court coordinates, inside-court flags, person trajectories, and track continuity | Box bottom-center approximates foot contact; a generic person detected in the court may be a player | Candidate crops, duration, observations, quality label, and review actions |
| Candidate building | Per-track observations, duration, detector scores, box size, court position, and movement | Fragment association by time, distance, speed, size, appearance histogram, and court side; `STRONG`/`USABLE`/`UNCERTAIN` quality | Similar fragments belong to one person; movement and in-court ratios distinguish likely players | At most four eligible candidates; user selects “This is me” |
| Analytics | Selected observations and their timestamps/court coordinates | Observed distance, average movement, average position, zone occupancy, heatmap, trajectory, observed duration, unobserved gaps, and fragment warnings | The selected/merged track is the user; calibration and detections are accurate enough for feet and zones | Distance, average movement, average position, zone percentages, heatmap, and trajectory |
| Match IQ | Persisted analytics fields and timeline positions | Threshold-based rule matches, ordered “top signal,” summary, and focus message | Fixed thresholds have player meaning; one second/three observations are adequate; rule priority means importance | Up to four insight cards, P-values, evidence metrics, focus, and generic limitations |
| Secondary UI | Persisted Match IQ summary, insight, and focus fields | “Latest” and “recent” Match IQ views; a share-card composition | Short excerpts remain honest without full limitations | Dashboard/performance summaries and share cards, often without limitations |

### Code evidence

- The real backend is a YOLO `person`-class detector with ByteTrack
  (`app/services/tracking/ultralytics_bytetrack_backend.py:15-83`). There is no paddle,
  racket, ball, or action detector.
- A person's image-ground point is the bounding-box bottom center and is transformed
  through court calibration (`app/services/video/player_analysis.py:496-538`).
- Candidate eligibility uses categorical quality, at least 65% in-court observations,
  at least 0.5 ft/s court movement, no more than three fragments, and a top-four policy
  (`app/services/candidates/service.py:961-1024`). These are heuristics, not a proof that
  a candidate is a player.
- Main distance counts only consecutive observations from the same raw track with gaps
  no greater than one second (`app/services/analytics/movement.py:292-313`). Zone time
  follows the same track/gap principle (`app/services/analytics/zones.py:38-74`).
- Analytics persists `source_fragment_count`, `observed_duration_seconds`,
  `unobserved_gap_seconds`, and `continuity_warnings`
  (`app/schemas/analytics.py:87-105`), but the Match IQ page does not render them
  (`web/components/analytics-details.tsx:59-243`).
- Match IQ is a deterministic ten-rule engine; it is not AI or an LLM
  (`app/services/match_iq/engine.py:1-168`).

### Integrity boundary

The most important distinction is that Court4 does not directly measure “player
positioning” in the tactical sense. It detects pixels, estimates a person's foot point,
maps that estimate to a calibrated court, associates observations into a candidate, and
then derives movement metrics. “Court4 measured” is honest only when those upstream
inferences and their uncertainty are also visible.

The recent top-four/in-court/movement filters are safer than the earlier broad candidate
list described in the reference reports. They reduce what users see, but no current
labeled evaluation establishes player-selection precision, tracking continuity accuracy,
or metric error on real videos. Filtering is not confidence calibration.

## Supported vs Unsupported Insights

The rating below evaluates the whole evidence chain, not whether arithmetic crosses the
configured threshold. “Show” means the evidence supports the claim in its present scope;
“weaken” means preserve only the literal observation with sample and confidence context;
“suppress” means do not present the current insight until its measurement is safe.

| Rule | Current claim type and evidence | Observation or interpretation | Enough evidence? | Rating | Decision |
| --- | --- | --- | --- | --- | --- |
| `positioning-high-baseline-v1` | Baseline occupancy is at least 55%; the percentage is time accumulated from continuity-safe in-court intervals | Direct derived measurement plus the interpretation that it is the largest “signal” | Enough to report the sample percentage, not enough to characterize match positioning without tracking quality and coverage | **Partially Supported** | **Weaken:** “In the observed sample…” and include duration, coverage, gaps, and measurement confidence |
| `positioning-high-kitchen-v1` | Kitchen occupancy is at least 55% | Direct derived measurement plus “largest signal” interpretation | Same limitation as baseline; no rally, point, or tactical context | **Partially Supported** | **Weaken** to a sample-qualified location observation |
| `positioning-high-transition-v1` | Transition occupancy is at least 55% | Direct derived measurement plus “largest signal” interpretation | It establishes where tracked time was assigned, not whether the player was caught in transition or played poorly | **Partially Supported** | **Weaken** and explicitly prohibit tactical interpretation |
| `positioning-low-transition-v1` | Transition occupancy is at most 20% | Direct derived measurement; “limited” is a threshold interpretation | The percentage is reproducible, but the 20% boundary has no validated performance meaning | **Partially Supported** | **Weaken** to the percentage and disclose that no good/bad conclusion follows |
| `positioning-balanced-zones-v1` | Every zone is between 20% and 45% | Interpretation of an arbitrary threshold band as “balanced” | No empirical or pickleball-outcome evidence validates that band as balance or quality | **Partially Supported** | **Weaken:** report the three percentages; do not imply desirable balance |
| `positioning-primary-zone-v1` | The maximum zone is below 55% and the distribution does not meet the “balanced” band | Direct comparison of zone percentages | Enough to identify the largest measured zone, but not to make it a tactical focus | **Partially Supported** | **Weaken** to a descriptive sample result |
| `movement-short-total-distance-v1` | Total observed distance is at most 10 ft | Interpretation of an absolute number as “short” | Distance is not normalized by observed duration or video coverage; 10 ft can mean stillness, a short sample, or tracking loss | **Partially Supported** | **Weaken** the number; do not infer sample length from distance |
| `movement-measured-distance-v1` | Distance, speed, and tracked seconds are repeated from analytics | Direct derived measurements | The metrics exist, but the statement pairs zone tracked time with speed calculated from `observed_duration_seconds`; those denominators can differ when selected observations fall outside the court | **Partially Supported** | **Weaken** and show each metric's denominator and coverage separately |
| `timeline-first-half-higher-distance-v1` | First timeline-span half is at least 1.25 times and 5 ft above the other | Derived comparison presented as a match-half observation | No. Timeline positions omit raw track IDs; the rule reconnects adjacent positions and can count fragment/gap jumps. “Half” is also the tracked span, not a game or match half | **Unsupported** | **Suppress** until continuity-safe and renamed to observed-span halves |
| `timeline-second-half-higher-distance-v1` | Second timeline-span half is at least 1.25 times and 5 ft above the other | Derived comparison presented as a match-half observation | No, for the same continuity and semantics reasons as the first-half rule | **Unsupported** | **Suppress** |

### Cross-cutting rule defects

1. **The sufficiency gate is not evidence-based.** Match IQ labels a report reliable after
   only three timeline observations and one second of tracked zone time
   (`app/services/match_iq/engine.py:15-16, 613-625`). No reference report or test
   establishes that these thresholds produce stable measurements.
2. **“Top signal” is rule order, not evidence strength.** Rules are sorted by fixed
   priority, truncated to four, and the first is called the top signal
   (`app/services/match_iq/engine.py:76-90, 560-568`). There is no statistical ranking,
   confidence comparison, or player relevance model.
3. **The summary miscounts its subject.** “Match IQ found N movement observations” counts
   emitted insight rules, not video/timeline observations.
4. **P10–P90 is internal priority.** The UI exposes it as `P{priority}`
   (`web/components/analytics-details.tsx:190-202`) without explaining that it is neither
   percentile, performance score, probability, nor confidence.
5. **Behavior tests prove deterministic output, not semantic validity.** Match IQ tests
   cover a generated case and a low-data case, but do not validate threshold meaning,
   real-video metric accuracy, confidence calibration, or fragment-safe half comparisons
   (`tests/test_match_iq.py`).

## Confidence Assessment

Court4 does not currently separate or propagate the five required confidence layers.

| Confidence layer | Current state | Integrity consequence |
| --- | --- | --- |
| Tracking confidence | Per-box detector confidence and track-average confidence exist. Court auto-detection also emits a heuristic confidence. | Detector confidence means confidence in a person box, not identity continuity or coordinate accuracy. Court-detection confidence is a hand-built geometry score, not a calibrated probability. Neither reaches Match IQ. |
| Candidate confidence | No numeric candidate confidence. `STRONG`, `USABLE`, and `UNCERTAIN` are threshold categories; association evidence records gaps, distance, speed, box ratio, and optional appearance similarity. | A `USABLE` candidate can still merge different people or omit the user. The selected candidate may have up to three fragments, but Match IQ does not disclose association uncertainty. |
| Measurement confidence | Absent. Analytics persists fragments, observed duration, unobserved gap time, and continuity warnings but not an error bound or quality grade. | A precise-looking `83.8%` or `69.1 ft` is shown without saying how much of the video was observed or how sensitive it is to calibration/tracking error. |
| Interpretation confidence | Absent. Fixed rule thresholds fire as binary truths. | Being barely above 55% is treated the same as a stable, well-observed 90%; one second can produce the same insight as a long, continuous sample. |
| Recommendation confidence | Absent. Focus messages have supporting insight IDs but no confidence, prerequisites, or abstention reason. | “Focus” can imply coaching even when only a location percentage exists and no outcome context is available. |

These layers are not interchangeable. A high-confidence person box can belong to the
wrong person; a correctly selected person can have fragmented coverage; a precise
movement measurement can still support no tactical interpretation; and a plausible
interpretation can still be too weak for practice advice. Collapsing the layers makes
Court4 look more certain as the pipeline gets further from direct evidence.

User selection is valuable identity evidence—someone explicitly chooses “This is me”—but
it does not validate automatic fragment merges, missed detections, court calibration, or
the accuracy of the resulting movement metrics.

## Recommendation Assessment

Court4 currently produces three possible focus-message families. None is genuine
coaching.

| Focus message | Classification | Evidence assessment | Required decision |
| --- | --- | --- | --- |
| `Focus area: positioning mix` — use the primary zone insight as the main movement focus | Educational navigation presented with coaching-adjacent framing | The selected rule supports where observed time was assigned. It does not establish that the zone caused a problem, mattered during rallies, affected points, or should be changed. | Keep only as “What to review.” Do not call it an improvement or practice focus without rally/outcome/opponent context. |
| `Focus area: movement sample length` — use a longer segment before treating Match IQ as a practice guide | Data-quality educational note | The caution is safe, but it is triggered by total distance at or below 10 ft, not by short duration, low coverage, or discontinuity. A long stationary sample can trigger it; a short noisy sample can avoid it. | Base any sample warning on duration, coverage, gaps, fragments, and metric stability. |
| `Focus area: measured movement` — review metrics and artifacts; no intent or shot-quality claim | Educational note | This is supported and appropriately restrained, but it does not tell a player what to improve. | Safe to retain as navigation, not coaching. |

### Missing context required for genuine coaching

Any claim that the player should move toward or away from a zone, cover more or less
distance, change pace, recover differently, or alter positioning would require at least
some of the following information that Court4 does not possess:

- rally boundaries and phases;
- ball position and trajectory;
- shot type, contact, and quality;
- serve/return context;
- point outcome and score;
- partner and opponent positions/actions;
- player intent and role;
- a validated skill-level or coaching baseline.

The current engine correctly avoids explicit claims about these subjects. The risk comes
from the labels “Match IQ,” “Top signal,” and “Focus area,” which can cause users to read
descriptive metrics as coaching despite the cautious body text.

## Limitation Assessment

### What Court4 tells users today

- It reports movement-only metrics.
- It says that shots, serves, rallies, ball movement, opponents, scoring, and intent are
  not evaluated.
- It says that previous matches are not compared because history is unavailable.
- When below the minimal gate, it reports too few observations or less than one second
  of tracked time.

These limitations are accurate and appear on the full analytics page.

### What is missing

- How much of the source video was reliably observed.
- Observed duration versus total video/match duration.
- Unobserved gap duration and whether multiple raw fragments were combined.
- Tracking quality, candidate quality, and fragment-association uncertainty.
- Court calibration source, quality, and likely coordinate error.
- Whether real-player selection was ambiguous or the recording was limited.
- Per-insight confidence and the reason for that confidence.
- A clear rule for when a result should not be trusted.
- A warning that person detection does not verify paddle possession or active play.
- A warning that zone labels are geometry, not tactical evaluation.

The analytics model already stores several of these facts, but the primary UI hides them.
This is an information-flow failure rather than solely a measurement gap.

### Where over-interpretation is likely

1. The full page calls raw movement facts “Your Match IQ.”
2. Decimal precision implies validated accuracy that the real-video reports do not
   establish.
3. “Top signal,” “largest positioning signal,” and “Focus area” imply relevance to
   performance.
4. P-values resemble a score, percentile, or confidence.
5. “First half” and “second half” sound like match structure even though they split the
   observed timestamp span.
6. Dashboard and performance pages repeat the Match IQ summary without its limitations
   (`web/components/dashboard-workspace.tsx:23-58`;
   `web/components/performance-workspace.tsx:17-85`).
7. Share cards include summary, insights, and focus but omit limitations and confidence
   (`web/lib/share-card.ts:59-100`). “Movement facts only” in the footer is helpful but
   does not disclose sample or tracking limitations.

## Understandability Assessment

For an ordinary pickleball player, the current Match IQ answers only the first of the
five product questions consistently.

| Player question | Can the current UI answer it? | Finding |
| --- | --- | --- |
| 1. What did Court4 observe? | **Mostly** | It shows distance, average movement, average position, zone percentages, and maps. It does not clearly say that these cover only reliable tracked intervals. |
| 2. Why does it matter? | **No** | Threshold crossings are not linked to rally context, outcomes, or a validated educational explanation. |
| 3. How certain is Court4? | **No** | No measurement, interpretation, or recommendation confidence is shown. |
| 4. What could Court4 not determine? | **Partly** | Generic missing capabilities are listed, but sample-specific tracking, calibration, identity, and coverage limitations are absent. |
| 5. What should I actually practice? | **No** | The focus messages are review prompts, not evidence-backed practice advice. |

### Confusing or overly technical language

- `P30`, `P70`;
- engine version `MATCH-IQ-RULES-V1`;
- “movement observations” when the count is actually insight count;
- “signal” and “top signal”;
- “tracked sample” without observed/total duration;
- “zone occupancy” and “transition zone” without a player-friendly definition;
- rule IDs, metric paths, and rule thresholds inside “Why Court4 said this”;
- “artifacts” and “intent” in a player-facing focus message;
- “average movement” without explaining the denominator or whether it means speed while
  visible, speed across the clip, or speed while moving.

Evidence transparency should remain available, but technical provenance should be
separate from a plain-language explanation.

## Intended Insight Model Assessment

| Layer | Current maturity | Assessment |
| --- | --- | --- |
| **Measurement** | Exists | Distance, position, occupancy, duration, gaps, and maps are calculated. Main distance and occupancy are continuity-aware, but real-world error is not quantified. |
| **Evidence** | Exists, incomplete | Insight cards name metrics and thresholds, and persisted artifacts are traceable. Upstream tracking/calibration/candidate quality is not part of the evidence bundle. |
| **Interpretation** | Thin and unvalidated | Rules label high, low, balanced, short, and half differences. Thresholds are deterministic but not validated against outcomes or player benefit. |
| **Confidence** | Missing | Component scores exist upstream, but there is no separated, propagated confidence model or per-insight abstention logic. |
| **Limitations** | Partial | Generic capability limits are honest; sample-specific and surface-consistent limitations are missing. |
| **Action** | Not yet present | Focus messages direct attention but do not provide genuine, evidence-backed practice action. |

The pipeline therefore stops between Evidence and defensible Interpretation. Adding a
language model now would improve prose while preserving—or amplifying—the same evidence
gaps.

## Maturity Scores

| Area | Score | Explanation |
| --- | ---: | --- |
| Evidence quality | **2/5** | Metrics have traceable source fields and main distance/zone calculations avoid known gaps. However, real-video tracking lacks labeled accuracy, paddle/player verification is absent, calibration error is not quantified, and timeline-half evidence is unsafe. |
| Insight integrity | **2/5** | The engine is deterministic, exposes rule evidence, and avoids unsupported shot/tactical claims. It still calls fixed priority a top signal, uses unvalidated thresholds, accepts one-second samples, and emits two continuity-unsafe rules. |
| Confidence model | **1/5** | Detector and court scores plus candidate categories exist, but the five confidence layers are neither separated nor propagated to Match IQ. |
| Recommendation safety | **3/5** | Current focus text is restrained and explicitly avoids intent/shot evaluation. It is still coaching-adjacent, and the sample-length advice uses distance as the wrong proxy. No current message is genuine coaching. |
| Understandability | **2/5** | Players can read the measurements, but not their reliability, meaning, limits, or practice consequence. Technical priority/version/rule language adds ambiguity. |
| Coaching readiness | **1/5** | Court-space movement is a useful prerequisite, but rallies, ball, shots, outcomes, opponents, and validated coaching relationships are absent. |
| AI readiness | **1/5** | Structured reports and evidence IDs are useful inputs, but unreliable/uncalibrated evidence, missing confidence, and no safe action schema make generated interpretation unsafe. |

## Current Phase

**Honest Movement Summaries**

This is the single best phase classification. Court4 is beyond only raw analytics because
it turns measurements into deterministic summaries, attaches metric evidence, explicitly
limits itself to movement, and abstains below a minimal data gate. It is not yet
Contextual Match IQ because it has no rally, ball, shot, outcome, opponent, or situational
context. It is not coaching because it cannot connect an observation to a validated
improvement action.

The phase label describes the product direction, not completion. Current summaries are
honest in intent and mostly descriptive, but they are not yet adequately qualified by
sample reliability and confidence.

## Biggest Integrity Risks

1. **Unsafe timeline-half measurements:** fragment/gap jumps can be counted as movement.
2. **Confidence disappears downstream:** raw detector/candidate/calibration quality is
   not carried into analytics decisions, Match IQ, or the UI.
3. **Minimal data is called reliable:** three observations/one second can produce a full
   Match IQ and focus.
4. **Person is treated as player by heuristic:** no paddle or active-play evidence exists;
   moving non-players and incorrect fragment merges remain possible.
5. **Precision without validated accuracy:** decimal distances and percentages look more
   certain than current real-video evidence warrants.
6. **Internal priority is presented as significance:** P-values and “Top signal” are not
   confidence or importance measures.
7. **Limitations are not surface-consistent:** dashboard, performance, and share surfaces
   can carry claims without the full-page caveats.
8. **Descriptive focus can be mistaken for coaching:** no result links zone/distance to
   rally success or a practice need.
9. **Real-world validation is not labeled:** the reference reports are observational and
   document failures, but there is no ground-truth benchmark for person selection,
   continuity, distance, occupancy, or insight correctness.

## Recommended Next Milestone

### Evidence-Calibrated Honest Movement Summary

The single highest-impact next phase is to finish the **Honest Movement Summaries** layer
with explicit evidence quality, confidence separation, and abstention. This should happen
before Contextual Match IQ, coaching, AI wording, or Player History.

### Why it matters

Court4 already has enough movement structure to give players a modest but useful answer:
“Here is what was observed, how much was observed, and how far you can trust it.” Today,
the system has much of that provenance internally but does not use it to decide whether
an insight is safe or show it consistently. Closing that gap improves honesty,
understandability, and user trust without pretending the product can coach from data it
does not have.

### Acceptance criteria

1. Every movement summary separates:
   - observation;
   - interpretation, if any;
   - measurement confidence;
   - interpretation confidence;
   - limitations;
   - action or explicit “no safe action.”
2. Confidence inputs include calibration source/quality, selected-candidate quality,
   detector/track quality, observed duration, source-video coverage, fragment count,
   unobserved gaps, and metric stability.
3. Each insight has a documented show/weaken/suppress gate and a plain-language abstention
   reason. One second/three observations cannot be called reliable without validation.
4. Timeline-half rules are either made continuity-safe using segment/track identity or
   remain suppressed. No metric may bridge an unobserved gap.
5. Distance and speed use and display the same explicit denominator; zone time is not
   substituted for general observed time.
6. The UI removes ambiguous priority presentation and distinguishes rule order from
   confidence. “Top signal” is used only if importance is actually measured.
7. Full results, dashboard, performance, and share surfaces preserve the minimum
   confidence and limitation context needed to prevent over-interpretation.
8. Plain-language output lets an ordinary player answer:
   - what was observed;
   - how much of the video was observed;
   - how certain Court4 is;
   - what Court4 could not determine;
   - whether any practice action is justified.
9. A labeled, versioned real-video validation set covers multiple cameras, orientations,
   lighting conditions, player sizes, spectators, occlusions, and fragmented tracks.
   It reports candidate precision/recall, identity-continuity errors, position/distance
   error, occupancy error, and insight show/weaken/suppress outcomes.
10. No output calls itself coaching or claims improvement until its action is supported
    by the required context and validation.

### Out of scope

- LLM or generative-AI summaries;
- Player History and cross-match trends;
- tactical coaching or personalized drills;
- ball tracking;
- rally, shot, serve, and point detection;
- opponent or partner analysis;
- scoring and outcome attribution;
- playstyle profiling;
- public sharing infrastructure.

AI should eventually communicate already-qualified evidence; it should not decide what
is true before Court4 has a reliable confidence and abstention model.

## Final Verdict

### PARTIALLY

**Can Court4 honestly market understandable, evidence-backed feedback as one of its core
features today? PARTIALLY.**

Court4 can honestly market **evidence-linked movement measurements and experimental
movement summaries** for controlled or clearly qualified recordings. The code preserves
metric provenance, handles continuity correctly in its main distance and occupancy
calculations, requires user identity selection, and discloses that it does not understand
shots, rallies, the ball, opponents, scoring, or intent.

It cannot yet market dependable improvement feedback, contextual Match IQ, or coaching.
The current product does not propagate confidence, does not show sample-specific
limitations, has no labeled real-video accuracy benchmark, accepts inadequately small
samples, exposes rule priority as if meaningful, and contains two unsupported timeline
rules. An ordinary player can see what Court4 calculated but cannot reliably determine
why it matters, how certain it is, when not to trust it, or what to practice.

The honest market position today is therefore narrower than the core vision: **Court4
provides experimental, evidence-linked movement observations—not yet validated coaching
or consistently understandable improvement insight.**

## Phase 1.4 Implementation Addendum — 2026-07-25

The Phase 1.4 implementation addresses the audit's principal code-level integrity
findings:

- upload preflight and analysis readiness are separate typed, persisted assessments;
- recording, tracking, measurement, interpretation, and recommendation confidence are
  separate categorical dimensions with factual rationales;
- every new insight separates observation, evidence, confidence, cautious
  interpretation, limitations, and review action;
- deterministic gates produce normal, cautious, measurement-only, or
  insufficient-evidence output;
- interpretation and advice are suppressed for limited evidence;
- unsuitable evidence receives no normal insight cards;
- rule priority, internal IDs, and reason codes are hidden from normal UI;
- the two timeline-half rules are disabled, so Match IQ no longer reconnects
  positions across unobserved gaps; and
- legacy analyses remain readable with conservative unavailable-quality defaults.

This addendum does not change the audit's validation caveat. The thresholds are initial
engineering safeguards and have not been calibrated against labeled videos or
measurement ground truth. Court4 remains an honest movement-measurement product, not a
coaching or tactical system.
