from fastapi import APIRouter

from app.api.v1.analyses import router as analyses_router
from app.api.v1.auth import router as auth_router
from app.api.v1.history import router as history_router
from app.api.v1.internal import router as internal_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(analyses_router)
router.include_router(history_router)
router.include_router(internal_router)

__all__ = ["router"]
