# Docker disk runbook

## Phase 1.8D0 measurement (2026-08-05)

Free space was 6,700,752,896 bytes before real-video validation, fell to
3,894,087,680 bytes after its generated evidence, and was 2,044,063,744 bytes after
the final frontend build and browser artifacts. Docker reported 29.78 GB of images,
379.6 MB of containers (209.6 MB reclaimable), 914.2 MB of volumes (effectively none
reclaimable), and 32.78 GB of build cache (8.922 GB reclaimable). The existing
`court4:local` content size is 3,161,053,009 bytes and Docker Desktop displays about
9.26 GB; it runs as root and has no image healthcheck.

Two explicitly identified D0 validation containers were removed and the isolated
test/spike PostgreSQL containers were stopped; no volume, upload, analysis, artifact, user media, or unrelated image
was deleted. Broad cache pruning and WSL VHD compaction were not performed because
the cache ownership is mixed and host compaction is a separate manual maintenance
window. The required 20 GiB build reserve was not reached. Accordingly, no image was
built from the ambiguous working tree.

Safe manual Docker Desktop/WSL maintenance: stop all workloads cleanly, verify and
back up named volumes, fully quit Docker Desktop, run `wsl --shutdown`, compact only
Docker Desktop's identified virtual disk using the vendor-supported host procedure,
restart Docker, and verify every named volume/container before cleanup is considered
complete. Never delete or recreate a PostgreSQL VHD/volume to reclaim space.

## 2026-08-05 pre-deployment measurement

Docker reported 29.78 GB of images, 257.5 MB of containers, 931.6 MB of volumes, and 32.78 GB of build cache, of which 8.922 GB was reclaimable. The host had only 8,061,038,592 bytes free. The existing `court4:local` image content size was 3,161,053,009 bytes (historical displayed Court4 image size about 9.26 GB), runs as root, and has no healthcheck. A source-current rebuild was intentionally not started because free space was below the 20 GB reserve. This is a release blocker, not permission to prune volumes or user data.

For staging, budget the image and temporary build layers separately from at least 25 GiB of persistent Court4 data, PostgreSQL, logs, and backups. Require an exact inventory before pruning, never run broad volume cleanup, and verify that the selected host retains at least 20 GiB of build reserve after required persistent allocations.

## Incident and cause

The host began with 11,830,042,624 bytes free. Docker reported 68.92 GB of build cache, dominated by repeated 8.87–8.95 GB Court4 dependency layers from detector/dev builds. Historical Court4 images were about 9.3 GB each. Court4 materially contributed most of the cache pressure because the optional detector installs PyTorch/CUDA libraries; database volumes (about 65 MB each), the 913 MB total volume set, and the roughly 0.91 GB workspace were not the cause. A test PostgreSQL container also needed slow crash recovery after the daemon interruption, but its data was intact.

This was a local Docker Desktop/WSL storage incident. It can recur in CI when builders have unlimited caches and can recur on a single production host if images/logs/artifacts have no retention, although managed registries and immutable deployment hosts change the failure mode.

## Safe inventory

Run before cleanup:

```text
Get-PSDrive C
docker system df -v
docker images --format "table {{.Repository}}:{{.Tag}}\t{{.ID}}\t{{.Size}}"
docker ps -a
docker volume ls
docker inspect <candidate>
docker logs --tail 200 <container>
```

Also inspect workspace `data/output`, `web/.next*`, test reports, Python caches and Docker Desktop's WSL virtual-disk/resource settings.

## Cleanup performed

After inventory, six unused historical Court4 image tags and the unused `court4:local` image were removed. No running image or unrelated-project image was removed. `docker builder prune --force` removed only dangling build cache and reported 53.73 GB reclaimed. All database, upload and artifact volumes were preserved. The PostgreSQL test volume was allowed to finish crash recovery rather than being deleted.

The final `court4:phase18c1` image is 9.26 GB. Final measurements were 10,402,066,432 host bytes free, 23.99 GB build cache (8.922 GB reclaimable), and 913.2 MB of volumes. Host free space did not increase because Docker Desktop retained the freed blocks inside its WSL virtual disk; offline VHD compaction is a separate host operation and was deliberately not performed.

## Prevention and never-delete rules

- Cap CI BuildKit cache and expire per-branch builders; publish one dependency layer rather than rebuilding detector extras per tag.
- Split CPU/API and optional GPU detector images in Phase 1.8E so the normal API does not inherit CUDA weight.
- Monitor host free bytes, Docker cache, image inventory and container JSON logs before builds; stop builds below an agreed reserve (20 GB recommended for this image shape).
- Expire development `.next`, Playwright, screenshots and synthetic analysis artifacts only after confirming they are generated.
- Never prune volumes broadly and never delete named PostgreSQL, uploaded-video, analysis-artifact, migration or unrelated-project volumes.
- Prefer exact image IDs/tags and dangling-cache pruning. Record before/after output in incidents.
