# Court4 Evidence UX Polish Report

Date: 2026-07-27

## Implementation verdict

Implemented as a frontend presentation-only pass. The evidence model, internal video
quality policy, analytics, Match IQ, Active Play shadow framework, calibration behavior,
thresholds, persistence, and API contracts are unchanged.

Player-facing copy now consistently uses “video.” Internal `recording_*` fields,
types, reason codes, policy versions, and artifact contracts retain their existing
names for backward compatibility.

Plan and terminology:

- `EVIDENCE_UX_POLISH_PLAN.md`
- `EVIDENCE_UX_COPY_GUIDE.md`

## Player narrative

The analytics page now follows:

Video Quality → Observation Coverage → Movement Measurements → Evidence Confidence
→ Movement Insight → Observed Court Position → Movement Maps → Limitations and
Video Guidance.

Video failures use specific player-facing explanations rather than upload
preflight, blocking-failure, candidate-span, or engineering-check language. The page
uses existing guidance and provides “Try another video” when the video is
unsuitable. Internal reason codes remain in persisted/debug data and are not rendered.

## Observation coverage

The frontend fetches the existing analysis job beside the existing analytics response.
Coverage is calculated only when persisted total video duration and
`observed_duration_seconds` are present, positive, and compatible. It shows video
length, reliably observed duration, percentage, uncertain duration, and persisted
tracking confidence.

Zero reliable duration is “Not available — not enough reliable tracking.” A missing
historical observed-duration field is “Legacy analysis — coverage unavailable.”
Unavailable coverage is never displayed as 0%. The page states that reliable tracking
coverage is not the amount of live gameplay.

## Confidence and insight

Video, Tracking, Measurement, Interpretation, and Recommendation remain separate.
They are displayed as an ordered dependency chain with icon, text label, and
High/Moderate/Low/Unavailable state; no overall score is introduced. Mobile uses a
vertical chain and desktop uses a horizontal chain.

Match IQ gates and behavior are unchanged. Player labels are:

- Verified movement insight
- Limited movement insight
- Measurement only
- Not enough evidence for insight

An unsuitable result explains why no Match IQ is shown and points back to the
continuity-safe measurements without presenting suppression as a system error.

## Position, maps, and limitations

Zone Occupancy is now Observed Court Position. Kitchen, Transition, and Baseline values
are unchanged, with explicit wording that they describe observed geometry rather than
positioning quality.

The heatmap is marked “Measurement only” and explains warmer/cooler frequency,
tracking gaps, video-quality context, and the absence of a ball path. The
trajectory is marked “Observed movement” and gives visible “Tracking started here”
and “Tracking ended here” legends outside the image so labels do not cover the path.

Limitations are deduplicated and grouped as Video, Tracking, and Analysis
limitations. Raw continuity codes are translated into player language. Analysis
limitations explicitly exclude shots, serves, rallies, ball movement, opponents,
scoring, outcomes, tactics, and intent.

## Accessibility

Status is communicated by icon and text as well as color. Sections use semantic
headings and lists; the confidence chain has an accessible label; coverage uses a
named progress element; long copy and cards use wrapping/min-width safeguards; map
legends include text; retry focus is visible; and the 390px browser scenario verifies
no horizontal overflow.

## Regression protections

- No backend, schema, persistence, analytics, Match IQ, calibration, or policy source
  was changed.
- Existing numeric distance, conversion, movement, average-position, and court-zone
  values are asserted unchanged in component tests.
- Suppression and share-card eligibility remain driven by the existing Match IQ gate.
- Active Play states, policy versions, and output are absent from the player page.
- Internal calibration remains absent from primary navigation.
- Current policy hashes, reviewer-label hash, and deterministic report hash remain
  verified.

## Validation

Final validation:

- `npm.cmd run lint`: passed with no warnings or errors.
- `npm.cmd run typecheck`: passed.
- `npm.cmd run test`: 18 files and 80 tests passed.
- `npm.cmd run build`: passed; the analytics route built at 11.2 kB with 138 kB
  first-load JavaScript.
- `npm.cmd run e2e`: 9 Playwright scenarios passed, including suitable/verified,
  measurement-only, unsuitable/retry, valid coverage, legacy coverage, mobile
  overflow, and the existing workflow.
- `docker run --rm court4:phase16a1 python -m pytest
  tests/test_movement_analytics.py tests/test_match_iq.py
  tests/test_recording_quality.py tests/test_api_workflow.py`: 33 backend regression
  tests passed.

Safety confirmation:

- readiness integrity reports production thresholds unchanged;
- reviewer-label hash unchanged;
- deterministic report status `MATCH`;
- no schema or backend contract changed;
- no analytics or Match IQ calculation source changed;
- no inference command ran during this pass;
- no Active Play state or internal calibration link appears in the player page or
  primary navigation.

Warnings and corrected failures:

- Vitest printed the upstream Vite CJS Node API deprecation warning.
- Playwright printed the existing `NO_COLOR`/`FORCE_COLOR` warning and slow-spec note.
- Backend tests printed one upstream Starlette `TestClient`/httpx deprecation warning.
- During the video-terminology refinement, one Vitest attempt found a stale upload
  guide copy assertion. The assertion was updated; the complete final suite then
  passed with no product-code failure.

## Known limitations

Coverage requires both a current analytics observed duration and the existing job’s
persisted video duration. If either is missing or inconsistent, Court4 abstains.
The map artwork itself is unchanged; start/end explanations are provided in an
accessible legend below the image.

## Recommended human review

Review the suitable, limited, unsuitable, and legacy pages with players unfamiliar
with Court4. Ask them to explain what was observed, what was measured, why insight may
be limited, and what they would change in their next video. Do not use this copy
review to alter evidence thresholds.
