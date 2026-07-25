# Court4 Track Continuity Report

Date: 2026-07-23

## Executive Summary

Phase 1.3B adds a deterministic player-candidate layer between raw
YOLO/ByteTrack output and player selection. Users now review visual candidate
cards, not detector track IDs. Candidates can contain multiple non-overlapping
track fragments, review decisions survive refresh and restart, and analytics
preserve fragment lineage without adding movement across observation gaps.

The controlled workflow is ready for a controlled real-match demonstration.
The real landscape result is materially easier to review, but it is not a
claim of identity recognition: low-resolution generic-person detections still
create duplicate and spectator candidates that require human review.

## Scope

This phase covers track-fragment continuity, candidate generation and review,
manual correction, candidate-based analytics, recording suitability, and the
existing landscape and vertical reliability cases. It does not add accounts,
cloud or database storage, background workers, biometric recognition, ball or
rally tracking, scoring, shot classification, or generated coaching.

## Current Tracking Architecture

- Ultralytics YOLO accepts class `0` (`person`) and feeds detections to the
  integrated ByteTrack tracker with `persist=True` and `bytetrack.yaml`.
- ByteTrack assigns raw IDs. Court4 persists all observations incrementally in
  `tracking/observations.jsonl` and the summary in `tracking/tracking.json`.
- The bottom-center of each bounding box is transformed through the calibrated
  homography to attach court coordinates and inclusion flags.
- The legacy selection filter uses duration, observation count, court
  inclusion, confidence, movement rate, and a candidate cap.
- The controlled JSON backend supplies deterministic fixture detections and
  IDs; the real backend derives both detections and IDs from YOLO/ByteTrack.
- Analytics previously consumed one selected raw ID. Identity resets therefore
  shortened analysis, while directly joining IDs would have invented jumps.

Observed fragmentation is primarily associated with ByteTrack identity resets
during occlusion, small/far subjects, people leaving and re-entering the frame,
and intermittent low-confidence detections. Vertical framing and calibration
perspective affect eligibility; resizing preserves aspect ratio and no evidence
of a letterboxing-specific coordinate bug was found.

## Candidate Architecture

`PlayerCandidateCollection` is a typed, schema-versioned document persisted at
`tracking/player_candidates.json`. Each candidate records a deterministic ID,
source fragments, observed times and duration, observed frames, in-court ratio,
court movement, average box size, court-side estimate, representative artifacts,
quality reasons and warnings, automatic merge evidence, and review state.

Candidate IDs are a SHA-256-derived value of the analysis ID and sorted raw
fragment membership. A stable grouping therefore produces a stable ID. Manual
merges have stable persisted IDs and separately recorded decisions. Legacy
analyses generate candidates lazily and map a legacy selected raw track to the
containing candidate.

## Fragment Association Rules

All thresholds are centralized in `AssociationThresholds`. Automatic
association is deterministic and requires:

- non-overlapping fragments;
- at most a 15-second gap;
- endpoint distance no greater than 14 feet;
- required speed no greater than 18 feet/second;
- bounding-box area ratio no greater than 1.75;
- no clearly opposite court sides;
- HSV appearance-histogram similarity of at least 0.70 when available;
- for gaps over 0.75 seconds, appearance similarity of at least 0.90 and at
  least 0.5 seconds of observations on both sides.

Any temporal overlap blocks an automatic group merge. Every raw fragment is in
exactly one generated candidate. Edges and groups use stable sort keys, so
regeneration is repeatable. Appearance is supporting evidence only; no
re-identification or biometric model was added.

## Candidate Quality Rules

Quality is categorical rather than a fake confidence percentage:

- `STRONG`: at least 5 seconds, at least 15 observations, at least 65% in
  court, at most three fragments, a preview, consistent side, and at least
  four feet of court-position span;
- `USABLE`: at least 1 second, at least three observations, and at least 30%
  in court;
- `UNCERTAIN`: available for review but below the usable rules;
- `REJECTED`: explicitly excluded by review.

Machine-readable warnings include short duration, low in-court ratio, high
fragment count, preview failure, small subject, inconsistent side, limited
court movement, and vertical-video limitation. The position-span rule prevents
stationary sideline detections from receiving a STRONG label based on
homography jitter alone.

## Manual Review Workflow

The match workflow shows ranked `Player N` cards with a crop, duration, court
side when reliable, quality, warning, `This is me`, `Not a player`, and
`Same player`. Preview details show up to three highlighted full frames from
early, middle, and late observations. Raw IDs appear only in collapsed
technical details.

Manual merge is a two-candidate confirmation. It blocks substantial duplicate
timestamps, incompatible court sides, excessive gaps, and implausible travel.
The persisted manual decision can be undone. Rejected candidates move to a
recoverable excluded section and can be restored. Selection, rejection,
restore, merge, and undo are refresh-safe filesystem operations.

## Analytics Integration

Movement analytics now consume all source fragments of the selected candidate
in chronological order. Within a frame, the highest-confidence observation is
used. Movement is counted only within a source fragment and only across gaps of
at most one second; no distance is added between fragments or across long
unobserved gaps. Zone time follows the same observed-interval boundary.

The report, summary, and timeline persist the selected candidate ID, fragment
count, technical raw IDs, observed duration, unobserved gap duration, and
continuity warnings. Match IQ still derives only from persisted analytics and
does not strengthen claims because fragments were combined.

## Recording Suitability

Video inspection records normalized rotation metadata and produces a typed
`SUITABLE`, `LIMITED`, or `UNSUITABLE` assessment. Orientation, resolution,
duration, detected people, and usable candidates contribute factual reasons
and guidance. A LIMITED video can continue. Court4 does not claim detector
failure before detection evidence exists.

## Landscape Real-Video Results

Source: `dc4b4effac81444da71bd848a51ed590`, 61.2 seconds, 640x368,
1,836 frames. CPU YOLO/ByteTrack run:
`phase13a-landscape-yolo-repro-20260722`.

```powershell
docker run --rm -v "${PWD}:/app" -w /app court4:phase13b `
  python -m scripts.build_player_candidates `
  --analysis-id phase13a-landscape-yolo-repro-20260722 `
  --tracking-report data/output/phase13a-landscape-yolo-repro-20260722/tracking/tracking.json `
  --observations data/output/phase13a-landscape-yolo-repro-20260722/tracking/observations.jsonl `
  --video data/output/dc4b4effac81444da71bd848a51ed590/uploads/source.mp4 `
  --metadata data/output/dc4b4effac81444da71bd848a51ed590/metadata.json `
  --tracking-dir data/output/phase13a-landscape-yolo-repro-20260722/tracking
```

| Measure | Phase 1.3A | Phase 1.3B |
| --- | ---: | ---: |
| Raw tracks | 161 | 161 (preserved observations) |
| Legacy eligible tracks | 4 | 4 (backward-compatible report) |
| Reviewable player candidates | N/A | 80 |
| Quality distribution | N/A | 5 STRONG, 25 USABLE, 50 UNCERTAIN |
| Recording suitability | N/A | LIMITED (`limited_resolution`) |
| Selection result | Four raw-ID cards | Visual candidates are selectable; no identity was selected during validation |

Examples of automatic fragment membership include `1,141`, `104,193`,
`243,296,299`, and `59,192,288`. One far-court candidate contains 15 short
fragments and is marked with `high_fragment_count`.

Representative-crop review found on-court subjects in all five STRONG
candidates. Both near-court players and both small far-court player appearances
are present in the ranked list. The obvious seated sideline spectator that had
previously ranked fourth is now USABLE with `limited_court_movement`, not a
primary STRONG candidate. Duplicate candidates for the same visible player and
additional spectator candidates remain; without labeled identity ground truth,
precision, recall, and a four-person grouping claim would be misleading.

The preserved raw tracking time was 168.623 seconds (127.764 seconds detector
time, 10.888 average processing FPS). Final candidate build time was 2.149
seconds and preview generation was 11.343 seconds, for 13.492 seconds of
post-processing and approximately 182.115 seconds combined. Candidate
post-processing was 8.0% of tracking time.

Selected-player viability is demonstrated by candidate selection/API/browser
coverage. Continuity correctness is demonstrated deterministically: the
fragment analytics test combines observed sections, reports the gap, and adds
no endpoint jump.

## Vertical Real-Video Results

Source: `f54693f1003849fdb456247322925258`, 14.4 seconds, 720x1280,
432 frames. CPU YOLO/ByteTrack run:
`phase13a-vertical-yolo-repro-20260722`.

```powershell
docker run --rm -v "${PWD}:/app" -w /app court4:phase13b `
  python -m scripts.build_player_candidates `
  --analysis-id phase13a-vertical-yolo-repro-20260722 `
  --tracking-report data/output/phase13a-vertical-yolo-repro-20260722/tracking/tracking.json `
  --observations data/output/phase13a-vertical-yolo-repro-20260722/tracking/observations.jsonl `
  --video data/output/f54693f1003849fdb456247322925258/uploads/source.mp4 `
  --metadata data/output/f54693f1003849fdb456247322925258/metadata.json `
  --tracking-dir data/output/phase13a-vertical-yolo-repro-20260722/tracking
```

Phase 1.3A produced two raw tracks and zero eligible raw tracks. One track was
outside the calibrated court; the on-court track failed the legacy global
movement-rate eligibility threshold (0.926 feet/second versus 1.2), rather
than failing person detection.

Phase 1.3B keeps those raw observations and produces:

- candidate `pc_c6aa6d87f6f40e0d`, raw track 2, 14.27 observed seconds,
  13.21 feet of movement, `USABLE`, selectable;
- candidate `pc_a3bb32bef20fe23a`, raw track 1, 14.37 observed seconds,
  zero in-court movement, `UNCERTAIN`.

Suitability is `LIMITED` with `vertical_video_limitation` and actionable
landscape/full-court/stability guidance. No global eligibility threshold was
weakened. Rotation metadata is normalized during inspection. Remaining limits
are the narrow vertical view, overlay, perspective, and low spatial coverage.
The preserved tracking time was 45.489 seconds; candidate build and previews
added 2.116 and 2.011 seconds, respectively.

## Controlled Fixture Results

Controlled coverage includes one-track candidates, deterministic multi-fragment
association, simultaneous-person separation, opposite-side and impossible-speed
blocking, quality classification, duplicate-timestamp manual-merge blocking,
manual merge/undo, rejection/restore, candidate selection persistence, legacy
raw-selection mapping, candidate analytics, gap preservation, and recording
suitability/orientation handling.

## Automated Validation

Final validation commands:

```powershell
docker build -t court4:local .
docker run --rm -v "${PWD}:/app" -w /app court4:local sh -c "python -m ruff check . && python -m ruff format --check . && python -m mypy app scripts tests && python -m pytest"
cd web
npm.cmd run lint
npm.cmd run typecheck
npm.cmd test -- --run
$env:NEXT_PUBLIC_COURT4_API_URL="http://127.0.0.1:8000"
$env:NEXT_PUBLIC_COURT4_MAX_UPLOAD_BYTES="1073741824"
$env:NEXT_PUBLIC_COURT4_SUPPORTED_VIDEO_EXTENSIONS=".mp4,.mov,.avi,.mkv"
npm.cmd run build
npm.cmd run e2e
```

Final results:

- Docker: `court4:local` built successfully;
- backend: 86 pytest tests passed with one upstream Starlette/httpx
  deprecation warning; Ruff check, 75-file Ruff format check, and mypy over 75
  source files passed;
- frontend: 71 Vitest tests passed; lint, typecheck, and production build passed;
- Playwright: five workflows covering the candidate happy path, fragmented
  candidate path, manual review, manual calibration, and missing-model recovery
  passed in 18.7 seconds;
- runtime: `/health` and `/docs` return HTTP 200.

## Performance Results

| Video | Tracking | Candidate build | Preview generation | Combined |
| --- | ---: | ---: | ---: | ---: |
| Landscape | 168.623 s | 2.149 s | 11.343 s | 182.115 s |
| Vertical | 45.489 s | 2.116 s | 2.011 s | 49.616 s |

Appearance descriptors decode each source once. Preview generation is skipped
for fragments below the one-second/three-observation review threshold, while
those fragments remain recoverable UNCERTAIN candidates.

## Defects Found and Fixed

- Raw identity resets propagated directly into selection and analytics.
- Joining selected raw IDs could create artificial cross-fragment movement.
- Legacy vertical filtering hid an otherwise reviewable on-court track.
- Preview generation initially decoded tiny fragments unnecessarily.
- Duration-first ranking promoted a stationary spectator because of coordinate
  jitter; STRONG quality now requires meaningful spatial coverage.
- Candidate review errors now use typed, recoverable API/UI states.
- Refresh could not previously preserve candidate corrections because the
  candidate domain and persistence document did not exist.

## Remaining Risks

- Generic YOLO person detection still includes spectators and background people.
- The landscape list has duplicate visible-player candidates and ambiguous
  long fragment chains; human review is still required.
- Appearance histograms are lighting/clothing cues, not identity recognition.
- Court-side estimates depend on calibration quality and were not reliable
  enough to infer match format in the landscape clip.
- Low-resolution far-court players remain highly fragmented.
- Processing is synchronous and CPU-bound.
- Real validation has no labeled player-identity ground truth.

## Readiness Verdict

`Ready for a controlled real-match demonstration`

The deterministic fixtures, review corrections, persistence, candidate-based
analytics, browser workflow, and vertical recovery support a supervised demo.
The remaining duplicate/spectator review load and unlabeled real-video accuracy
prevent a limited design-partner pilot. The recommended next phase is focused
real-video continuity hardening with labeled tracks, review-list reduction,
and broader camera/lighting validation—not Player History.
