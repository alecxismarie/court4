from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.persistence.runtime import get_persistence
from app.schemas.health import HealthResponse, ReadinessResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse}},
)
def readiness() -> ReadinessResponse | JSONResponse:
    try:
        ready = get_persistence().service.ready()
    except Exception:
        ready = False
    if ready:
        return ReadinessResponse(status="ready", database="ok")
    payload = ReadinessResponse(status="not_ready", database="unavailable")
    return JSONResponse(status_code=503, content=payload.model_dump(mode="json"))
