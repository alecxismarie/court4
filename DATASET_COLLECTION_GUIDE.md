# Court4 Calibration Dataset Collection Guide

## Collection objective

Collect 20–30 consented recordings that exercise Court4's documented recording-quality
and evidence boundaries. The objective is calibration coverage, not a highlight reel
and not a claim of general accuracy.

## Recommended composition

Use the balance report as a warning system, not a quota optimizer. Aim for:

- 10–15 indoor and 10–15 outdoor recordings;
- both singles and doubles;
- at least five examples of each `EXCELLENT`, `GOOD`, `LIMITED`, and `UNSUITABLE`
  outcome, with final labels assigned only after review;
- mostly landscape recordings plus several intentional vertical examples;
- baseline and diagonal camera positions;
- near, medium, and distant camera placement;
- both 720p and 1080p source recordings;
- stable tripod footage and clearly unstable handheld footage;
- none, minor, moderate, and severe obstruction;
- scenes with and without spectators or irrelevant people; and
- strong and fragmented tracking outcomes.

Twenty samples cannot perfectly populate every cross-product. Prioritize distinct
failure modes and record unknown metadata honestly.

## Dataset splits

Assign the split before inspecting threshold-simulation gains:

- `DEVELOPMENT`: approximately 60% for exploratory policy analysis;
- `VALIDATION`: approximately 20% for review after a proposal is formed; and
- `HOLDOUT`: approximately 20%, kept untouched until the proposed policy is fixed.

For 25 recordings, a reasonable starting split is 15 development, 5 validation, and 5
holdout. Do not move difficult validation or holdout samples into development to improve
results.

## Consent and privacy

Before recording or retaining footage:

1. Obtain permission from the court or facility and informed consent from identifiable
   players.
2. Tell participants the footage will be used to evaluate computer-vision behavior.
3. Avoid recording minors unless a legally appropriate guardian process is in place.
4. Avoid names in filenames and manifests; use stable pseudonymous sample and player
   IDs.
5. Record whether spectators may appear and minimize unnecessary bystander capture.
6. Remove audio when it is not needed and may contain private conversation.
7. Define who may access the original video, how long it is retained, and how deletion
   requests are handled.

The repository is not a secure media store. Consent records and private identity keys
must not be committed here.

## File handling

- Keep large and private videos outside Git.
- `external_video_reference` may contain an organization-managed opaque reference, not
  credentials or signed URLs.
- `local_video_reference` must be repository-relative and should point only to an
  ignored local file.
- Persisted analysis references belong under the configured relative artifact root.
- Never copy a video merely to make a manifest path convenient.
- Never commit access tokens, personal names, cloud URLs containing credentials, or
  machine-specific absolute paths.
- Back up reviewer manifests separately from replaceable generated reports.

The onboarding template distinguishes video references from artifact references.
`MISSING`, `PARTIAL`, and legacy artifacts are valid workflow states and should not be
hidden.

## Recording procedure

For every recording:

1. Note indoor/outdoor, singles/doubles, orientation, resolution, FPS, camera position,
   distance, lighting, stability, obstruction, and court visibility.
2. Keep the entire court visible when collecting ideal examples.
3. For boundary examples, change one major property where practical—for example,
   distance or obstruction—rather than degrading everything at once.
4. Capture enough continuous play for meaningful tracking without requiring rally or
   ball annotation.
5. Preserve the original media metadata.
6. Assign a stable sample ID before analysis.
7. Run the existing analysis workflow once and preserve the resulting analysis IDs.

Do not manufacture a quality label from the current Court4 output. Human reviewers
should assess the recording independently.

## Onboard a recording

Generate a template:

```powershell
python -m scripts.calibrate_evidence template outdoor-diagonal-01 `
  --output calibration/reviews/outdoor-diagonal-01.json
```

Then:

1. Replace the placeholder inspection analysis ID.
2. Add known recording metadata and safe video references.
3. Add stage-specific persisted analysis IDs.
4. Assign the dataset split.
5. Review identities, intervals, and insights using `ANNOTATION_GUIDE.md`.
6. Copy the validated sample object into `calibration/manifest.v2.json`.
7. Validate the individual sample and the complete manifest.
8. Review balance, incomplete labels, mappings, and artifact compatibility.
9. Regenerate reports.

The CLI refuses to overwrite an existing template unless `--force` is explicitly used.
Do not use `--force` on a file containing completed human review.

## Quality control

- Use two independent reviewers for the gold subset.
- Preserve each initial review outside the merged manifest.
- Adjudicate disagreements without erasing the fact that disagreement occurred.
- Spot-check candidate mappings against the video, not against Court4's ranking alone.
- Do not mark `REVIEWED` until required metadata and the intended annotation scope are
  complete.
- Keep holdout labels hidden from threshold proposal work where operationally possible.
