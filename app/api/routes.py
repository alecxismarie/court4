import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.persistence.runtime import get_persistence
from app.schemas.health import HealthResponse, ReadinessResponse

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse}},
)
def readiness() -> ReadinessResponse | JSONResponse:
    database_ready = False
    storage_ready = False
    try:
        persistence = get_persistence()
        database_ready = persistence.service.ready()
        storage_ready = persistence.storage.ready()
    except Exception:
        pass
    if database_ready and storage_ready:
        return ReadinessResponse(status="ready", database="ok", storage="ok")
    logger.warning(
        "readiness_check_failed",
        extra={
            "database": "ok" if database_ready else "unavailable",
            "storage": "ok" if storage_ready else "unavailable",
        },
    )
    payload = ReadinessResponse(
        status="not_ready",
        database="ok" if database_ready else "unavailable",
        storage="ok" if storage_ready else "unavailable",
    )
    return JSONResponse(status_code=503, content=payload.model_dump(mode="json"))
