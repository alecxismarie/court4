from fastapi import APIRouter

from app.api.v1.analyses import router as analyses_router

router = APIRouter()
router.include_router(analyses_router)

__all__ = ["router"]
