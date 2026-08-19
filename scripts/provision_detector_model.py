from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from app.services.tracking.model_provisioning import (
    DETECTOR_MODEL_FILENAME,
    DETECTOR_MODEL_IDENTIFIER,
    DETECTOR_MODEL_SHA256,
    provision_pinned_detector_model,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Provision Court4's pinned player-detector model with checksum verification."
    )
    parser.add_argument(
        "--destination",
        type=Path,
        default=Path("models") / DETECTOR_MODEL_FILENAME,
    )
    args = parser.parse_args(argv)
    provision_pinned_detector_model(args.destination)
    print(
        f"Provisioned {DETECTOR_MODEL_IDENTIFIER} at {args.destination} "
        f"(sha256:{DETECTOR_MODEL_SHA256})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
