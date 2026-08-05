from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.config import get_settings

CONFIRMATION = "quarantine-expired-court4-uploads"


@dataclass(frozen=True)
class CleanupReport:
    mode: str
    root: str
    expired_directories: tuple[str, ...]
    candidate_files: int
    candidate_bytes: int
    quarantined_directories: tuple[str, ...]


def inspect_expired_uploads(root: Path, *, older_than_hours: int) -> tuple[list[Path], int, int]:
    upload_root = root.expanduser().resolve() / "_uploads"
    if not upload_root.is_dir():
        return [], 0, 0
    cutoff = datetime.now(tz=UTC) - timedelta(hours=older_than_hours)
    expired: list[Path] = []
    total_files = 0
    total_bytes = 0
    for directory in sorted(path for path in upload_root.iterdir() if path.is_dir()):
        files = sorted(path for path in directory.rglob("*") if path.is_file())
        newest = max((path.stat().st_mtime for path in files), default=directory.stat().st_mtime)
        if datetime.fromtimestamp(newest, tz=UTC) >= cutoff:
            continue
        expired.append(directory)
        total_files += len(files)
        total_bytes += sum(path.stat().st_size for path in files)
    return expired, total_files, total_bytes


def run_cleanup(
    root: Path,
    *,
    older_than_hours: int,
    apply: bool,
    confirmation: str | None,
    max_files: int,
    max_bytes: int,
) -> CleanupReport:
    resolved_root = root.expanduser().resolve()
    expired, total_files, total_bytes = inspect_expired_uploads(
        resolved_root,
        older_than_hours=older_than_hours,
    )
    relative = tuple(path.relative_to(resolved_root).as_posix() for path in expired)
    quarantined: list[str] = []
    if apply:
        if confirmation != CONFIRMATION:
            raise ValueError("Cleanup refusal: exact quarantine confirmation is required.")
        if total_files > max_files or total_bytes > max_bytes:
            raise ValueError("Cleanup refusal: candidate scope exceeds the configured safety cap.")
        quarantine_root = resolved_root / "_quarantine" / "uploads"
        quarantine_root.mkdir(parents=True, exist_ok=True)
        for source in expired:
            destination = quarantine_root / source.name
            if destination.exists():
                raise ValueError("Cleanup refusal: quarantine destination already exists.")
            shutil.move(str(source), str(destination))
            quarantined.append(destination.relative_to(resolved_root).as_posix())
    return CleanupReport(
        mode="quarantine" if apply else "dry-run",
        root=str(resolved_root),
        expired_directories=relative,
        candidate_files=total_files,
        candidate_bytes=total_bytes,
        quarantined_directories=tuple(quarantined),
    )


def main() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Dry-run-first Court4 upload cleanup.")
    parser.add_argument("--root", type=Path, default=settings.local_storage_root)
    parser.add_argument("--older-than-hours", type=int, default=24)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm")
    parser.add_argument("--max-files", type=int, default=100)
    parser.add_argument("--max-bytes", type=int, default=5 * 1024**3)
    args = parser.parse_args()
    report = run_cleanup(
        args.root,
        older_than_hours=args.older_than_hours,
        apply=args.apply,
        confirmation=args.confirm,
        max_files=args.max_files,
        max_bytes=args.max_bytes,
    )
    print(json.dumps(asdict(report), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
