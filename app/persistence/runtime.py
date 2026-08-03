from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from hashlib import sha256
from uuid import UUID

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.persistence.database import create_database_engine, create_session_factory
from app.persistence.service import PersistenceService, RunProvenance
from app.persistence.storage import LocalStorage


@dataclass(frozen=True)
class PersistenceRuntime:
    engine: Engine
    session_factory: sessionmaker[Session]
    service: PersistenceService
    storage: LocalStorage
    _bootstrap_owner_user_id: UUID | None = None

    @property
    def owner_user_id(self) -> UUID:
        if self._bootstrap_owner_user_id is None:
            raise RuntimeError(
                "No development bootstrap owner is configured; pass an authenticated owner."
            )
        return self._bootstrap_owner_user_id


@lru_cache
def get_persistence() -> PersistenceRuntime:
    settings = get_settings()
    engine = create_database_engine(settings)
    session_factory = create_session_factory(engine)
    fingerprint_payload = {
        "pipeline_version": settings.pipeline_version,
        "schema_version": settings.persistence_schema_version,
        "policy_version": settings.policy_version,
        "tracking_backend": settings.default_tracking_backend,
        "frame_interval": settings.frame_processing_interval,
        "detector_confidence": settings.detector_confidence_threshold,
    }
    service = PersistenceService(
        session_factory,
        RunProvenance(
            pipeline_version=settings.pipeline_version,
            schema_version=settings.persistence_schema_version,
            policy_version=settings.policy_version,
            configuration_fingerprint=sha256(
                json.dumps(fingerprint_payload, sort_keys=True).encode()
            ).hexdigest(),
            software_commit_identifier=settings.software_commit_identifier,
            deployment_build_identifier=settings.deployment_build_identifier,
        ),
    )
    owner_user_id: UUID | None = None
    if settings.bootstrap_user_enabled:
        from app.persistence.bootstrap import configured_bootstrap_identity

        owner_user_id = service.ensure_bootstrap_user(configured_bootstrap_identity(settings))
    return PersistenceRuntime(
        engine=engine,
        session_factory=session_factory,
        service=service,
        storage=LocalStorage(settings.local_storage_root),
        _bootstrap_owner_user_id=owner_user_id,
    )
