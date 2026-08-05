from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.config import get_settings
from app.persistence.reconciliation import StorageReconciler
from app.persistence.runtime import get_persistence


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only Court4 storage reconciliation.")
    parser.add_argument("--output", type=Path, help="Optional JSON report path.")
    args = parser.parse_args()

    settings = get_settings()
    runtime = get_persistence()
    report = StorageReconciler(runtime.session_factory, settings.local_storage_root).reconcile()
    payload = json.dumps(report.as_dict(), indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{payload}\n", encoding="utf-8")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
