# Court4 Product Roadmap

Court4 is an evidence-first sports video analytics platform for athletes, coaches, and people who play the sport. The product should be reliable, truthful, and useful. It must never present a measurement more confidently than the evidence supports.

The product sequence is deliberate:

> Video → Computer Vision → Verified Evidence → Deterministic Analytics → AI Interpretation

Verified computer-vision and structured evidence remain the source of truth. AI may interpret that evidence later; it must not invent events, measurements, tactics, or conclusions.

This roadmap sets direction without dates or release promises. Pickleball is the primary supported sport. Padel is the next target for full feature parity, but remains gated until explicitly enabled. Additional sports are outside the current roadmap.

## Current — Pickleball reliability and integrity

Court4 is stabilizing the complete Pickleball path before expanding scope. The repository currently supports:

- email/password authentication, email verification, session security, and owner-scoped access;
- PostgreSQL as the durable authority for accounts, analyses, workflow state, provenance, artifacts, lifecycle, and idempotency;
- private local/S3-compatible object storage, repository-managed processing workspaces, checksum validation, and source/artifact lifecycle controls;
- browser-to-object-storage multipart uploads with recovery, renewal, completion verification, and duplicate handling, plus script/operator-driven abandoned-upload reconciliation; the repository does not establish scheduled execution;
- explicit analysis, run, stage, source-media, and whole-match lifecycle behavior with concurrency protection;
- YOLO/Ultralytics person detection with ByteTrack association, player-candidate construction, selection, rejection, and persisted manual “Same player” consolidation;
- deterministic Pickleball movement and court-position analytics with evidence/readiness gates;
- generated Match IQ based on versioned deterministic rules and structured analytics, with weak evidence suppressing interpretation or recommendations;
- owner-scoped Analysis History plus evidence-qualified Play History and Progress projections, including honest incomplete, excluded, provisional, and insufficient-history states;
- repository-managed workspace use for S3-backed tracking, analytics, and manual calibration instead of legacy output paths;
- separate generated and human-verified court calibration states, checksum-bound confirmation, stale-calibration invalidation, and row-version/concurrency protection.

These capabilities still require real-world validation across representative recordings. Repository implementation and automated tests are evidence of system behavior; they are not proof of computer-vision accuracy or product usefulness in every venue and camera condition.

## Premium Court Vision — active direction

The current active direction is more reliable automatic Pickleball court calibration. The existing contour/quadrilateral detector can assign high shape confidence to incorrect court-floor geometry, so detector confidence cannot serve as semantic proof.

The intended upgrade combines:

- semantic Pickleball court landmarks and keypoints;
- visible outer-line and non-volley-zone line validation;
- deterministic template, topology, and geometry checks;
- agreement across suitable frames from a stationary shot;
- the existing manual confirmation and correction flow as the safety fallback.

Work begins with an offline benchmark and dataset foundation. The repository now has unfinished Phase 1 benchmark work for a 12-keypoint/eight-line annotation contract, unchanged-detector replay, independent point/line errors, grouped outcomes, and deterministic reports. Its manifest intentionally contains no reviewed real labels yet. Model training, production integration, automatic verification, and threshold changes are later decisions that require measured evidence.

## Padel full support

After the shared Pickleball foundation is sufficiently stable, Court4 should bring Padel toward feature parity in:

- court recognition and calibration;
- player tracking, candidate construction, and player selection;
- evidence-backed analytics;
- report and History behavior;
- Match IQ;
- Progress when evidence quality supports comparison.

Authentication, ownership, uploads, lifecycle, generic video processing, low-level tracking contracts, and storage can be reused where their semantics remain valid. Court geometry, walls/glass, reflections, zones, rules, calibration evidence, eligibility, and tactical interpretation must remain sport-specific. Current Padel analyses are experimental and gated; they do not receive Pickleball calibration, movement, Match IQ, or Play History semantics.

## Court + Player + Ball intelligence

The long-term analytical model is:

> Court + Player + Ball + Time

Ball evidence should eventually place movement in context. Movement alone must not be treated as tactical meaning. Current ball tracking is optional, experimental, shadow-only evidence and is disabled by default. It must not affect trusted Match IQ, History, Progress, or player-facing analytics until representative validation supports that use.

## Evidence-backed AI Match IQ

AI interpretation comes after trustworthy structured evidence. A future AI layer may explain supported patterns, strengths, weaknesses, tactical observations, and training suggestions. Every claim must be traceable to verified evidence and deterministic analytics, carry appropriate limitations, and abstain when support is missing.

Current Match IQ is deterministic and rule-based. A generative AI/VLM system is not the present geometric or analytical authority.

## Real-user validation

Private alpha and beta validation should include real Pickleball players, then Padel players as its sport path becomes safe, and eventually coaches. Evidence collection should cover different devices, venues, lighting, orientations, camera positions, resolutions, occlusions, and recording conditions.

Success means people repeatedly receive trustworthy, understandable, useful analysis. Repeat use, correction behavior, failure recovery, and confidence in the evidence matter more than novelty.

## Monetization foundation

Monetization follows reliability and meaningful user validation. The intended product direction is:

- a free entry experience;
- a Pro subscription;
- a possible Coach or higher tier later;
- fair usage rules so rejected or unusable analyses do not unfairly consume paid allowance.

Product entitlements should remain provider-neutral. Payment providers grant or revoke Court4 entitlements; product code should not encode provider-specific access semantics.

## Payments and mobile distribution

The intended future channel model is:

- Court4 Web → Stripe;
- Android / Google Play → Google Play Billing;
- both → one Court4 entitlement system.

Stripe, Play Billing, subscription tiers, and this shared entitlement system are future architecture, not current implementation.

## Launch readiness

Launch readiness depends on trustworthy analysis, understandable evidence-quality warnings, predictable processing and recovery, privacy and data lifecycle behavior, fair monetization, and validation with real users. Publishing an app or placing it in Google Play is not, by itself, launch readiness.

Before broad launch, Court4 should demonstrate that it can:

- accept, process, retry, and delete private recordings predictably;
- preserve owner isolation and explain data retention;
- distinguish supported measurements from unavailable or provisional results;
- correct or abstain from bad court geometry;
- expose processing and failure state honestly;
- deliver reports that players and coaches understand and choose to use again.

## Queued performance investigation

**Match IQ/report latency audit:** determine why a completed analysis can take noticeable time to surface Match IQ or report content. Separate pipeline processing time from artifact persistence/materialization, API/report fetch, cache behavior, and frontend rendering. Evaluate progressive rendering where it presents already-available evidence sooner without disguising the true processing state.
