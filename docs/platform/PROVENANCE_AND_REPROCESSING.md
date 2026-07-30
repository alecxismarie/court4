# Provenance and Reprocessing

## Provenance envelope

Every `AnalysisRun` freezes the source and executable decision context before work
starts. Required immutable fields are specified in
[DATA_MODEL.md](DATA_MODEL.md#analysis_runs). The configuration fingerprint is:

```text
sha256(canonical_json({
  analysis_schema,
  pipeline,
  policies,
  model digests,
  tracker,
  court/calibration algorithms,
  normalized non-secret settings
}))
```

Canonical JSON uses sorted keys, UTF-8, stable numeric formatting, and no secrets,
host paths, signed URLs, or credentials. Store the canonical safe configuration in
`provenance_json` and its digest in the indexed column.

## Field classification

| Field group | Classification |
| --- | --- |
| Run number, source video checksum, all version strings/digests, config fingerprint, commit/build ID, creation/start time | Immutable |
| Lease, heartbeat, current status before terminal state, failure details | Mutable with state-event record |
| Completed/failed/cancelled timestamp | Set once on terminal transition |
| Artifact checksum, size, object version, schema version | Immutable after commit |
| Analysis title and user presentation settings | Mutable; not provenance |
| `Analysis.current_run_id`, supersession pointer | Mutable promotion pointer, audited |
| Historical missing version | Legacy fallback (`UNVERSIONED`/nullable) plus explicit limitation |
| Report URLs and signed URLs | Derived, never provenance |

Existing versions—Recording Quality, analytics, Match IQ, candidate, Active Play,
contribution, comparability, grouping, aggregation, trend, interpretation, and
calibration readiness—map into the run bundle. Missing current fields such as model
digest, software commit, and configuration fingerprint become mandatory for new
runs.

## Reprocessing

Reprocessing creates a new `AnalysisRun` for the same logical `Analysis` and source
video:

1. authorize owner and validate source retention;
2. create run `n+1` with `reprocessed_from_run_id`;
3. freeze the new provenance bundle;
4. process into distinct immutable object keys;
5. retain the old run and artifacts;
6. after successful commit, promote `current_run_id`;
7. optionally set an explicit supersession relationship and reason.

A failed reprocess leaves the previously completed run current. History uses the
current completed run by default but can reconstruct what was shown under any prior
policy/run. APIs added later should allow an owner to inspect prior runs.

A materially different user intent may create a new `Analysis` with
`reprocessed_from_analysis_id` rather than a run—for example, a future different
analysis subject. Pipeline upgrades alone use a new run.

## History integrity

Contribution and comparability decisions are calculated from the selected run's
recorded evidence and policy versions. A policy upgrade must not rewrite old report
bytes. It may:

- calculate a versioned projection at read time;
- persist a rebuildable projection cache keyed by owner, projection version, and
  source run/version fingerprint;
- create a reprocess run when new raw evidence is required.

Mixed versions retain the current conservative behavior: exclude or mark
provisional; never silently normalize incompatible evidence.

## Checksums

- Source video: streaming SHA-256 after upload completion.
- Detector model and static policy bundles: SHA-256 at run preparation.
- Every artifact: SHA-256 over stored bytes before metadata commit.
- JSON reports: checksum exact canonical persisted bytes, not a reserialized model.
- Multipart object ETags are not content checksums and are stored separately.

Checksums detect integrity/reconciliation problems; they do not prove authenticity
without trusted metadata and access controls.

## Legacy fallback

Imported filesystem analyses preserve their IDs and timestamps when valid. Unknown
values are explicit (`legacy-import-v1`, `UNVERSIONED`, or nullable according to
column rules) and listed in `provenance_json.legacy_missing_fields`. Import time,
source path hash, importer version, and reconciliation checksum are recorded.
Legacy values are never invented from the current runtime configuration.
