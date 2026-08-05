# Restricted staging infrastructure requirements

Status: **DEFINED, NOT PROVISIONED**. No cloud resources were created.

Court4 currently requires a single Linux x86-64 host with Docker Engine 27 or newer
(local validation used Engine 29.6.2),
8 dedicated vCPU and 16 GiB RAM minimum (24–32 GiB recommended). A GPU is not
required for the validated one-at-a-time CPU profile, but the measured 61.2-second
sample spent about 195 seconds in tracking. Low-cost memory-limited or ephemeral
managed hosting is unsuitable for the current approximately 9.26 GB image/CV stack.

Provision at least:

- 100 GiB system disk, retaining 20 GiB free before builds for image layers/cache;
- 50 GiB persistent application-storage disk mounted outside container layers;
- 20 GiB PostgreSQL storage, private-network only;
- 50 GiB encrypted backup storage in a separate failure domain;
- Ubuntu 24.04 LTS or another supported current Linux distribution;
- one backend instance, one active upload, and one active analysis job.

Expose 443 through a TLS 1.2+ reverse proxy; port 80 may redirect to 443. Do not
expose PostgreSQL or internal/test routes. Use final DNS such as
`staging.court4.example` and `api.staging.court4.example`, replacing both placeholders
before launch. Allow outbound TCP 443 to Brevo and required package/monitoring
endpoints. Set ingress size/timeouts consistently with the application upload limit.

Back up PostgreSQL daily for 14 days and weekly for 8 weeks; protect a consistent
filesystem backup or snapshot separately. Retain application/proxy logs for 14 days
without tokens or message bodies. Monitor backend availability, `/health`, `/ready`,
PostgreSQL connectivity, free disk, storage writes, upload/analysis failures,
processing duration, Brevo failure category, 5xx rate, restarts, backup success, and
reconciliation findings. Alert before the 10 GiB warning and page at the 5 GiB hard
stop. Every image/deployment must record commit, build ID, environment, migration
revision, pipeline version, model/tracker version, and configuration fingerprint.
