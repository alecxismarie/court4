# Consent and Data Use Architecture

Court4 must prove the terms in force and the user's acceptance before accepting
video bytes. This document defines records and gates, not agreement language or a
claim of legal compliance.

## Agreement model

Use immutable `AgreementVersion` records plus `ConsentAcceptance` records. Separate:

1. required platform terms/privacy acceptance for account and service processing;
2. account-level optional product-improvement purposes;
3. upload-time representation that the uploader owns or may upload the recording
   and has handled applicable participant/venue permissions.

Optional purposes are distinct values, not one broad boolean:

- debugging/support access;
- calibration;
- evaluation;
- product improvement;
- model improvement/training;
- anonymized/aggregated metrics.

Product operation is not evaluation permission. Support/debug access is not product
improvement permission. Product improvement is not model-training permission. A
recording approved for one purpose must not be copied into another purpose's dataset
without a separate, current acceptance for that purpose.

A user can use the core service without optional model-improvement consent unless
product/legal explicitly decides otherwise. Do not bundle optional permission into
required terms.

## Upload gate

Before upload reservation:

- user is verified and active;
- current required agreement version is accepted;
- upload representation for the current version is accepted/confirmed;
- optional purpose selections are stored independently;
- the server records agreement IDs/versions, content hashes, purpose categories,
  actor, timestamp, and acceptance source.

The upload records the acceptance IDs applied at creation so later agreement changes
do not obscure original provenance.

## Withdrawal and replacement

Withdrawal sets `withdrawn_at` and records the replacing acceptance when applicable.
It never edits the original agreement or acceptance. Optional withdrawal creates
dataset exclusion and cleanup work. A replacement required agreement becomes
effective prospectively; product policy decides whether existing users must
re-accept before new uploads.

## Required product/legal decisions

- uploader ownership or permission representation;
- responsibility for visible opponents and spectators;
- minors and guardian permission;
- jurisdiction/venue recording consent;
- required versus optional purposes;
- human debugging access and approval;
- calibration/evaluation/model training distinctions;
- raw and artifact retention;
- deletion and withdrawal consequences, including derived models;
- use and reversibility of anonymized/aggregated metrics;
- whether per-upload confirmation is always required;
- agreement change notification and re-acceptance;
- support, security hold, and dispute preservation;
- wording for generated artifacts that may show other people.

## Audit and minimization

Store the minimum proof needed. IP prefix and user-agent hash are optional and require
approval. Never put agreement text only in application code; persist an immutable
content hash and retrievable version. Never log raw consent tokens or entire legal
documents on each request.

## Ball feasibility boundary

Court4 does not yet have the auditable database records described above. Therefore
existing private-alpha, tester, or friend uploads are **not eligible by default** for
ball-model evaluation or training. Phase 1.9A0 adds no training-data ingestion path.

The offline ball-visibility feasibility validator accepts only a 2–3 clip manifest
whose every clip identifies a purpose-specific `model_evaluation` acceptance and has
no withdrawal timestamp. Those references must be reviewed against the external
source of consent before the dataset is used; the manifest is evidence routing, not
a substitute for the future consent ledger. Training remains a separate, ungranted
purpose even when evaluation consent exists.
