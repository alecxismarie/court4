# Court4 Evidence UX Copy Guide

## Voice

Explain what Court4 could observe before describing what it measured or interpreted.
Use calm, specific language. An evidence limitation is not a system error and is not a
judgment about player performance.

## Preferred player-facing terms

| Avoid | Use |
| --- | --- |
| Recording / recording quality | Video / Video Quality |
| Upload preflight / blocking failure | Video check / why this video is limited |
| Normal Match IQ is suppressed | Why no Match IQ is shown |
| Zone occupancy | Observed Court Position |
| Tracked candidate span | Reliably observed sample |
| Insufficient evidence badge | Not enough evidence for insight |
| Engineering threshold/check | Video or tracking requirement |

Internal reason codes, policy names, thresholds, candidate IDs, and calibration IDs
remain available only to development surfaces. Internal schema and code identifiers
continue to use `recording_*` where required for backward compatibility; those names
must not be rendered in normal player-facing copy.

## Narrative order

Video Quality → Observation Coverage → Movement Measurements → Evidence Confidence →
Movement Insight → Observed Court Position → Movement Maps → Limitations and Video
Guidance.

## Evidence rules

- Show coverage only when persisted video duration and observed duration are both
  available and compatible.
- Show `Not available`, never `0%`, when reliable coverage cannot be established.
- Mark missing historical duration fields as `Legacy analysis — coverage unavailable`.
- State that observation coverage is not active-gameplay coverage.
- Keep Video, Tracking, Measurement, Interpretation, and Recommendation confidence
  separate and show the dependency order.
- Label maps as measurements. Explain frequency colors, start/end markers, gaps, and
  the absence of ball-path information.
- Group and deduplicate limitations as Video, Tracking, and Analysis limitations.
