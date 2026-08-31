from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import select

from app.persistence.models import UploadSession, utc_now
from app.persistence.object_storage import MultipartObjectStorage, ObjectStorageError
from app.persistence.runtime import get_persistence

CONFIRMATION = "abort-expired-court4-multipart-sessions"
RECONCILABLE_STATES = ("initiated", "uploading", "expired")


@dataclass(frozen=True)
class MultipartCandidate:
    upload_session_id: str
    owner_user_id: str
    status: str
    storage_key: str
    expires_at: str


@dataclass(frozen=True)
class MultipartReconciliationReport:
    mode: str
    candidates: tuple[MultipartCandidate, ...]
    aborted_session_ids: tuple[str, ...]
    failed_session_ids: tuple[str, ...]


def reconcile_expired_multipart_uploads(
    *, apply: bool, confirmation: str | None, max_sessions: int
) -> MultipartReconciliationReport:
    if apply and confirmation != CONFIRMATION:
        raise ValueError("Reconciliation refusal: exact abort confirmation is required.")
    runtime = get_persistence()
    now = utc_now()
    with runtime.session_factory() as session:
        records = list(
            session.scalars(
                select(UploadSession)
                .where(
                    UploadSession.status.in_(RECONCILABLE_STATES),
                    UploadSession.expires_at <= now,
                )
                .order_by(UploadSession.expires_at, UploadSession.id)
            )
        )
    if len(records) > max_sessions:
        raise ValueError("Reconciliation refusal: candidate scope exceeds the safety cap.")
    candidates = tuple(_candidate(record) for record in records)
    if not apply:
        return MultipartReconciliationReport("dry-run", candidates, (), ())

    storage = cast(MultipartObjectStorage, runtime.storage)
    aborted: list[str] = []
    failed: list[str] = []
    for snapshot in records:
        try:
            storage.abort_multipart_upload(
                key=snapshot.storage_key,
                upload_id=snapshot.provider_upload_id,
            )
        except ObjectStorageError:
            failed.append(str(snapshot.id))
            continue
        if _mark_aborted(snapshot.id, now):
            aborted.append(str(snapshot.id))
    return MultipartReconciliationReport("abort", candidates, tuple(aborted), tuple(failed))


def _mark_aborted(upload_session_id: UUID, now: datetime) -> bool:
    runtime = get_persistence()
    with runtime.session_factory.begin() as session:
        record = session.scalar(
            select(UploadSession).where(UploadSession.id == upload_session_id).with_for_update()
        )
        if record is None or record.status not in RECONCILABLE_STATES:
            return False
        record.status = "aborted"
        record.failure_reason = "expired_session_reconciled"
        record.aborted_at = now
        record.updated_at = now
        record.row_version += 1
        return True


def _candidate(record: UploadSession) -> MultipartCandidate:
    return MultipartCandidate(
        upload_session_id=str(record.id),
        owner_user_id=str(record.owner_user_id),
        status=record.status,
        storage_key=record.storage_key,
        expires_at=record.expires_at.isoformat(),
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Dry-run-first reconciliation for expired Court4 multipart sessions."
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm")
    parser.add_argument("--max-sessions", type=int, default=100)
    args = parser.parse_args()
    report = reconcile_expired_multipart_uploads(
        apply=args.apply,
        confirmation=args.confirm,
        max_sessions=args.max_sessions,
    )
    print(json.dumps(asdict(report), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
