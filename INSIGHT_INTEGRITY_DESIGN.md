# Court4 Phase 1.4 — Insight Integrity Design

## Purpose and scope

Court4 reports movement evidence from a user-selected person track. It does not infer
shots, rallies, tactics, causes, intent, point outcomes, or opponent behavior. Phase 1.4
makes that boundary enforceable in data contracts and deterministic quality gates.

All thresholds in this phase are **initial engineering thresholds**. They are intended to
prevent obviously weak evidence from producing strong claims. They are not calibrated
probabilities and must be validated against labeled real videos before being described as
scientific, coaching, or performance standards.

## Canonical insight contract

Every newly generated Match IQ insight contains:

| Field | Contract |
| --- | --- |
| `observation` | A literal description of a measured value in the observed sample. |
| `evidence` | Typed source metrics, displayed values, and the deterministic rule condition. |
| `confidence` | Five separate confidence dimensions with a level and factual rationale. |
| `interpretation` | An optional, cautious description of what the observation may mean. |
| `limitations` | Per-insight reasons the observation must not be generalized. |
| `action` | An optional review step. It is navigation or recording advice, not tactical coaching. |

`title`, `id`, `rule_id`, and `priority` remain machine-facing traceability fields. Rule
IDs and priority are hidden from normal user views. `statement` is retained as a
backward-compatible alias of `observation` for persisted Phase 1.3 reports.

### Confidence dimensions

Each dimension is independent and uses `HIGH`, `MODERATE`, `LOW`, or `NOT_AVAILABLE`.
These are deterministic categories, not probabilities.

- **Recording confidence**: orientation, resolution, FPS, duration, and final recording
  quality.
- **Tracking confidence**: selected candidate quality, visible/in-court ratio, observed
  duration, fragments, and gaps.
- **Measurement confidence**: whether continuity-safe measurements have enough usable
  time and observations for the reported metric.
- **Interpretation confidence**: whether Court4 has enough evidence to offer a cautious
  sample-level interpretation. Movement-only rules never receive `HIGH`.
- **Recommendation confidence**: whether a safe next review step is supported.
  Tactical or causal advice is always unavailable because Court4 lacks the required
  rally, ball, outcome, opponent, and intent evidence.

## Evidence-quality gates

The report and every emitted insight receive one of four gates:

1. **`NORMAL`** — good or excellent recording/readiness, continuous usable evidence,
   and a supported sample-level observation. Interpretation may be cautious; actions
   remain review-only.
2. **`CAUTIOUS`** — evidence is usable but has a material warning. Observation and
   evidence are shown; interpretation is explicitly qualified.
3. **`MEASUREMENT_ONLY`** — the literal measurement is usable, but interpretation or
   advice is not. `interpretation` and recommendation/action are suppressed.
4. **`INSUFFICIENT_EVIDENCE`** — recording/readiness has a blocking failure or the
   measured sample is too small. Normal insight cards are suppressed.

The weakest relevant layer wins. A high detector box score cannot raise candidate
identity, continuity, calibration, interpretation, or recommendation confidence.

## Suppression rules

- `UNSUITABLE` analysis readiness produces `INSUFFICIENT_EVIDENCE` and no normal
  insights.
- Fewer than three valid court observations, less than one second of continuity-safe
  tracked time, or no calibrated court measurement suppresses all insights.
- `LIMITED` readiness, a fragmented selected candidate, a high gap ratio, or a short
  observed sample produces at most `MEASUREMENT_ONLY`.
- A `GOOD` recording with a usable but imperfect candidate produces at most `CAUTIOUS`.
- Interpretation is absent for `MEASUREMENT_ONLY` and `INSUFFICIENT_EVIDENCE`.
- Action is absent when recommendation confidence is `LOW` or `NOT_AVAILABLE`.
- First-half/second-half distance rules are disabled. The persisted timeline lacks
  fragment identity, so it cannot safely reconnect movement across unobserved gaps.
- No rule may claim that a movement pattern is good, bad, optimal, causal, tactical, or
  representative of a match.

## Match IQ rule contract

Every rule must:

1. name only metrics already persisted by analytics;
2. state the observation in sample-qualified language;
3. attach the exact metric and threshold used;
4. accept the report quality gate and confidence dimensions;
5. provide explicit limitations;
6. omit interpretation and action when its gate requires suppression;
7. avoid tactical, causal, comparative, and outcome claims;
8. remain deterministic and covered by tests;
9. never silently bridge tracking fragments or unobserved time; and
10. remain backward-readable if the schema evolves.

## Legacy behavior

Legacy jobs and analytics without preflight, readiness, or Phase 1.4 Match IQ fields
remain readable. They are labeled as having unavailable quality evidence and cannot be
upgraded to a stronger claim merely because old fields are absent. Existing persisted
Match IQ JSON is normalized with conservative defaults by the schema.
