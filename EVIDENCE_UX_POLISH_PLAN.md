# Court4 Evidence UX Polish Plan

## Audit

The analysis page currently exposes technical assessment language such as “upload
preflight,” “blocking failures,” “engineering checks,” and “suppressed.” Measurements,
confidence, interpretation, limitations, and maps are presented as neighboring cards
rather than a dependency story. Coverage exists in persisted duration fields but is
not explained. Confidence dimensions are disconnected, map captions are terse, zone
occupancy sounds evaluative, and limitations repeat inside insights and the report.

## Implementation

1. Present video quality first with plain-language reasons and recovery guidance.
2. Derive observation coverage only from persisted video and observed durations;
   explicitly distinguish unavailable and legacy analyses.
3. Order measurements, the five-stage confidence chain, insight eligibility, observed
   court position, maps, and grouped limitations as one evidence-to-insight narrative.
4. Keep all metrics, gates, rules, thresholds, schemas, artifacts, and Active Play
   behavior unchanged.
5. Test valid/unavailable/legacy coverage, all confidence labels, unsuitable and
   measurement-only states, maps, grouped limitations, accessibility, mobile layout,
   hidden internal codes, and unchanged values.
