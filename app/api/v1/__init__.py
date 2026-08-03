from fastapi import APIRouter

from app.api.v1.analyses import development_router as analyses_development_router
from app.api.v1.analyses import router as analyses_router
from app.api.v1.auth import development_router
from app.api.v1.auth import router as auth_router
from app.api.v1.history import router as history_router
from app.api.v1.internal import router as internal_router
from app.config.settings import Settings


def create_api_v1_router(settings: Settings) -> APIRouter:
    router = APIRouter()
    router.include_router(auth_router)
    router.include_router(analyses_router)
    router.include_router(history_router)
    if settings.environment in {"development", "test"}:
        router.include_router(development_router)
        router.include_router(analyses_development_router)
        router.include_router(internal_router)
    return router


__all__ = ["create_api_v1_router"]
