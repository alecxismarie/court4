# Court4 detector model provisioning

Court4's player detector uses one pinned external artifact. The model binary remains
ignored by Git; release source records its identity and verifies its bytes.

## Pinned identity

| Field | Value |
|---|---|
| Model | Ultralytics YOLO11 nano detection weights (`yolo11n.pt`) |
| Court4 identifier | `ultralytics-yolo11n-assets-v8.3.0` |
| Upstream release | Ultralytics assets `v8.3.0` |
| Source | `https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt` |
| Size observed | `5,613,764` bytes |
| SHA-256 | `0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1` |

The URL is versioned rather than a moving `latest` endpoint. The SHA-256 digest is
the authority: a successful HTTP response alone is not accepted as provenance.

## Local provisioning

Run from the repository root:

```powershell
python -m scripts.provision_detector_model --destination models/yolo11n.pt
```

The command downloads to a temporary file in the destination directory, verifies
the pinned checksum, and only then atomically replaces the target. A failed download
or mismatch leaves no accepted model. The `models/` directory remains ignored.

## Private staging provisioning

Build the backend image from the exact release SHA. Attach a writable persistent
model volume to a one-off command using that image, then run:

```bash
python -m scripts.provision_detector_model --destination /app/models/yolo11n.pt
```

After it succeeds, mount the same volume read-only at `/app/models` in the API
service and configure:

```dotenv
PICKLEBALL_AI_DEFAULT_TRACKING_BACKEND=ultralytics
COURT4_DETECTOR_MODEL_PATH=/app/models/yolo11n.pt
COURT4_DETECTOR_MODEL_SHA256=0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1
```

When `ultralytics` is the default backend, application creation verifies the file
before serving requests and fails clearly if it is missing or invalid. Explicit
Ultralytics analysis requests repeat verification immediately before loading YOLO.
No analysis path asks Ultralytics to locate or download weights by model name.

To recover a corrupt or lost model volume, provision a fresh volume with the same
one-off command and swap mounts only after the checksum succeeds. Do not copy a
developer-machine model path into deployment configuration.
