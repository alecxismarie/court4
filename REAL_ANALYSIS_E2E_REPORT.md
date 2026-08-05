# Real analysis browser E2E report

Status: **CLOSED** for one restricted single-instance CPU flow; capacity remains
conservative and the sample itself was honestly classified unsuitable for Match IQ.

## Sample and execution

- Approved existing sample: `data/output/dc4b4effac81444da71bd848a51ed590/uploads/source.mp4`
- SHA-256: `841D992DCA4A1D29D233EE3DBECAAFCD0235DEF1BAB4CB4722209AB0D24EC4FB`
- Size/duration/dimensions: 7,991,681 bytes; 61.2 seconds; 640x368 at 30 fps
- Scene: indoor doubles, camera behind the baseline
- Browser/API/database: real local frontend, current source-mounted API, disposable
  `court4_test`, isolated storage; no analysis API mocks
- Analysis ID: `7de6f35d28124d96b2298b3e4b985ec6`

The browser uploaded the video, persisted it, detected the court, ran Ultralytics
tracking, found candidates, selected a player, generated analytics, opened heatmap
and trajectory artifacts, refreshed, verified Analysis History and honest Play
History exclusion, logged out/in, and confirmed a second user received 404 for the
analysis and artifact.

## Timing and evidence

| Stage | Approximate duration |
|---|---:|
| Upload to calibration completion | 2.5 s |
| Tracking/player discovery | 194.6 s |
| Analytics/artifacts | 7.7 s |

The final analysis state was completed/analyzed. It produced 317 registered artifact
rows, including accessible heatmap and trajectory outputs. Court confidence was
0.966 and four candidates were selectable from 161 raw person detections. The
selected candidate had 16.97 seconds observed, 8.83 seconds of gaps, and two track
fragments. The evidence-readiness result was **UNSUITABLE**, so Movement
Measurements were shown while Match IQ and Play History contribution were honestly
suppressed.

The first full run completed the pipeline but its last UI assertion used an obsolete
label. After correcting the assertion to `Estimated movement path`, a resume-mode
browser run proved refresh, artifacts, histories, logout/login persistence, and
cross-user denial. A second full processing attempt was correctly rejected with a
typed 507 after host free space fell below the 5 GiB hard stop. This is capacity
control evidence, not a second successful analysis. CPU staging must therefore be
sized for about 3.5 minutes for this 61-second sample and limited to one job.
