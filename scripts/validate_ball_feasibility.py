from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from app.services.ball_tracking.feasibility import (
    FeasibilityDatasetError,
    validate_feasibility_dataset,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate a consent-cleared manual ball-visibility feasibility dataset."
    )
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        summary = validate_feasibility_dataset(args.manifest)
    except FeasibilityDatasetError as exc:
        parser.error(str(exc))
    print(json.dumps(summary.__dict__, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
