# Pickleball candidate-source inventory and provenance assessment

Assessment date: 2026-10-02

This is a local inventory, not dataset collection. It records source relationships and observed diversity that can be established from repository-managed metadata, local legacy analysis artifacts, hashes, and lightweight human inspection of existing sampled JPEGs. It does not select pilot frames, establish ground truth, evaluate the detector, or authorize use of any source.

## Evidence boundary

- Phase 1 Offline Benchmark Foundation: **COMPLETE and unchanged**.
- 120-frame Dataset Pilot Preparation: **COMPLETE and unchanged**.
- 120-frame collection/review: **NOT STARTED**.
- Reviewed-real manifest: **0 frames**.
- Pilot review ledger: **0 actual data rows**.
- No remote object-store inventory was attempted. Local files do not prove current Railway/S3 state or usage rights.
- `data/output` is treated only as an existing local legacy-artifact source for this assessment. It is not a new dataset location or a substitute for authorized repository/object-storage access.

## Method and fact classes

The machine-readable inventory is `candidate-source-inventory.csv`. Each source row separates:

- **established metadata:** local bytes, SHA-256 identity, inspection metadata, artifact paths, and exact-copy relationships;
- **derived metadata:** nominal sample times derived from frame number and recorded FPS, plus duplicate counts derived from hashes;
- **human inventory assessment:** conditions visible in the existing sampled images, without treating visual similarity as proof of shared venue, court, recording, or camera identity; and
- **unknown metadata:** usage/retention authority, origin, physical identities, and other facts the repository does not establish.

Stable recording and recording/camera group IDs are source-hash-scoped. The three group IDs prevent accidental merging while cross-recording relationships remain unknown. Their existence does not prove three independent physical cameras, courts, or venues.

## Established source inventory

| Count | Result |
| --- | ---: |
| Candidate real source recordings with distinct source-video SHA-256 hashes | 3 |
| Conservative source-scoped recording/camera groups | 3 |
| Physical court identities established by provenance | 0 |
| Venue identities established by provenance | 0 |
| Physical camera setup identities established by provenance | 0 |
| Pilot-eligible sources now | 0 |
| Questionable sources pending usage/provenance resolution | 3 |
| Ineligible real sources | 0 |

The sources are 171.108489 seconds at 640x368 landscape, 61.2 seconds at 640x368 landscape, and 14.4 seconds at 720x1280 portrait. All three contain real Pickleball imagery. The first includes edited promotional/score material, the second supplies only three heavily correlated 30-second samples, and the third supplies one portrait sample with a large text overlay. All remain `questionable` because dataset-use and retention authority is absent and physical court, venue, camera, and shot provenance is incomplete.

## Existing sampled-image material

The local scan found **179 sampled-frame JPEG files in 144 analysis directories and 24 exact SHA-256 image groups**. These are storage copies, not independent conditions.

- **10 unique real-image hashes / 29 files** trace to the three source hashes in `candidate-source-inventory.csv`.
  - Source `b58534780122...`: 6 unique images, 6 files.
  - Source `841d992dca4a...`: 3 unique images, 21 files across seven repeated analyses; 18 files are redundant exact copies.
  - Source `dd3f1f214ddb...`: 1 unique image, 2 files across two repeated analyses; 1 file is a redundant exact copy.
- **14 unique fixture hashes / 150 files** are blank/tiny or synthetic court-drawing validation material. They are not real candidate data and are excluded from the source CSV and pilot consideration.

The 14 excluded fixture hashes are:

```text
17e488719b376ac6ec6b0179e0256840ae261d75b86f1ebd063eb6d440551e66
1a02ac6cad70f66537773d87e7e10a12315e82cd0c2293239f789f61b85c5877
25f86748db4a482d52450613043326ab816ba17efd6399762f4b4c7062f4375b
2f451b349912f71b78f1b7b9c54c7e1037079bb6a0013cf923d1923a90636643
3913ff0918fd9b32c6e78eef6f5ace60542228af85bbc6196afa66540f976283
7ad4b1567384e2177c99ea8db785972604388a6febe630d4b07333bff8a3e863
8363c12c3c689f8f3592e70b4b858f5f65c770d4e1704cd5e8486bc35f0859f2
87109dc1fda59ec2f26fd942c63a1ed0aed5065f109eb0d48aa6b5c48ea08019
cb4d7cc3cfba844270bb4d37dbbb9bd6d3e410a4a2202356c7109a83d646d103
d6a5e838edfc11e308fadd38dc9b46da63346383e0436ae33491f05446c82eac
d7b68d518ef4d0a38c2f593b8d7d2690274b1328d11c382b389f91365e7a9398
ed3319e19a84e95d10c0c28414d9cb7e15c65ad7db8602d472444a5d11913648
ef17eea28cc371b2551125c75aae1cc4251f67c3c3dfc3577f595af07afa80d6
f04c2d4ddd738afc7e53d1857f16d4e0d142aa5c9b1f794b1ad726eaff160971
```

No exact duplicate exists among the 10 unique real-image hashes. Their 29 copies are highly correlated: they come from only three source recordings, and 19 are exact redundant copies. The six samples from the longest source include two nonclean promotional/score-overlay moments. The three samples from the 61.2-second source show one centered stationary-looking view at nominal 30-second spacing. The single portrait sample cannot establish temporal diversity. Provenance is insufficient for pilot selection until usage authority and grouping facts are resolved.

## Diversity supported by current evidence

The following are human inventory assessments unless explicitly described as recorded metadata:

| Dimension | Established or observed now | Limitation |
| --- | --- | --- |
| Recordings | 3 distinct source-byte hashes | Usage eligibility is unknown for all three. |
| Recording/camera groups | 3 conservative source-scoped groups | Physical camera independence and cross-source relationships are unknown. |
| Courts | At least two visibly different court environments: orange/red covered-court imagery and a blue indoor court | No physical court identity is provenance-backed; the two covered recordings must not be merged or counted as distinct courts from appearance alone. |
| Venues | Covered bright environment and enclosed indoor environment are visible | Venue identity is 0; covered indoor/outdoor status is ambiguous. |
| Camera view | One centered landscape baseline family, one moderate-diagonal landscape family, and one centered portrait family are visible | Exact placement, height, lens, movement, and shot boundaries are unknown. |
| Resolution/orientation | Two 640x368 landscape sources; one 720x1280 portrait source | No 720p/1080p landscape source is established. |
| Lighting | Bright diffuse covered light and strong artificial indoor light are visible | No provenance-backed lighting classification; difficult shadow/glare/mixed/low-light coverage is not established. |
| Court/line appearance | Orange/red with white lines, blue with white lines, blue NVZ in one source | Narrow color range; worn/colored/low-contrast lines are absent or unknown. |
| Competing markings | Adjacent courts and surrounding white markings are visible in the covered sources; multiple courts are visible indoors | Counts suitable for the required pilot are not established. |
| Occlusion | Players and nets obscure portions of target lines in existing samples | Only three correlated source groups; severity and quota coverage are not established. |
| Crop/overlays | Portrait framing and large text overlays are visible; edited promotional and score material occurs | Original capture and transformation history is unknown; clean candidate availability is not established for the short portrait source. |
| Negative/decoy | One promotional frame lacks usable court geometry | It has not been selected or independently reviewed as a no-target/decoy pilot frame. |

No current evidence establishes outdoor footage, elevated camera views, low camera views, difficult glare/shadow coverage, worn or low-contrast lines, eight physical courts, five venues, or 20 independent recording/camera groups.

## Pilot feasibility against the committed protocol

### Sufficient now

- Local source-byte identity, dimensions, duration, FPS, sampled-frame relationships, and exact image hashes can be established for three real recordings.
- Existing imagery demonstrates that the future candidate pool should consider centered, diagonal, portrait, adjacent-court, occluded, overlay, and promotional/decoy conditions.
- Exact duplicate copies have been identified and can be prevented from inflating a future inventory.

These facts support provenance cleanup and future candidate assessment only. They do not make any frame pilot-eligible today.

### Insufficient

- **Eligible sources:** 0 because dataset-use and retention authority is not recorded.
- **Recording/camera groups:** 3 source-scoped groups versus at least 20 required. Even if all three become eligible, the maximum-eight-per-recording rule permits at most 24 frames, not 120.
- **Physical courts:** 0 provenance-established versus approximately 8 required by the maximum-16-per-court cap.
- **Venues:** 0 provenance-established versus approximately 5 required by the maximum-24-per-venue cap.
- **Clean real sampled material:** 10 unique images, of which some contain overlays or no usable court view, versus 120 reviewed frames across fixed 50/40/20/10 strata.
- **Quality:** both landscape sources are 640x368; the only 720-pixel-width source is portrait and short.
- **Required strata and desired diversity:** current material cannot support or demonstrate the routine, challenging, abstention, negative, environment, lighting, camera-height, competing-marking, occlusion, crop, and resolution coverage in the protocol.

### Unknown

- Whether any current source may legally and operationally be retained for this dataset.
- Whether the two covered-court recordings share a venue, physical court, event, camera, or upstream source.
- Exact court, venue, camera-placement, height, lens, shot-boundary, edit, crop, and resize provenance.
- Whether unsampled portions contain eligible clean frames or additional independent shots. This task did not extract or inspect new frames.
- Current remote object-store availability and metadata. No remote access was attempted.

## Required source-footage additions

Before building the pilot, Court4 needs:

1. Usage/retention authority and provenance records for every retained source; otherwise exclude all three current sources.
2. At least **17 additional independent recording/camera groups** if all three current groups become eligible, and more if any do not. The final set must still meet all recording and stationary-shot caps.
3. Provenance-backed coverage totaling at least **8 physical courts** and **5 venues**. Because current court and venue identities are unestablished, none can yet be credited toward those minima.
4. Confirmed indoor and outdoor sources, with enough eligible material to pursue the desired 30-frame coverage for each rather than relying on ambiguous covered-venue imagery.
5. Multiple documented camera heights and positions, including centered baseline, moderate diagonal, and elevated/low variations where safe and representative.
6. 720p/1080p landscape footage plus varied perspective and quality; current landscape sources are only 640x368.
7. Purposeful condition coverage for difficult shadows, glare, mixed/low light, different court and line colors/contrast, worn lines, competing sport/court markings, meaningful occlusion, and partial cropping.
8. Eligible source material capable of filling the exact 50 routine supported, 40 challenging supported, 20 partial/ambiguous, and 10 no-target/visual-decoy strata without detector-driven selection.

The present inventory cannot satisfy the 120-frame protocol. This conclusion is about source availability and provenance only; it is not a detector accuracy result or a prototype-gate evaluation.

## Actions explicitly not performed

- No final pilot frame was selected, copied, or extracted.
- No candidate was added to `manifest.v1.json` or the review ledger.
- No court keypoint or line label was created or reviewed.
- No detector replay or geometric evaluation was run.
- No model was trained or introduced.
- No production code, benchmark code, schema, configuration, deployment, storage lifecycle, or remote object was changed.
