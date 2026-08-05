from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.auth import VerifiedUser
from app.config import get_settings
from app.config.settings import Settings
from app.schemas.history import PlayHistoryResponse
from app.services.history import HistoryProjectionService
from app.services.jobs import AnalysisJobRepository

router = APIRouter(prefix="/play-history", tags=["play-history"])

SettingsDependency = Annotated[Settings, Depends(get_settings)]


def get_history_service(
    settings: SettingsDependency, user: VerifiedUser
) -> HistoryProjectionService:
    repository = AnalysisJobRepository(
        output_dir=settings.analysis_output_dir,
        api_base_path=settings.api_base_path,
        owner_user_id=user.id,
    )
    return HistoryProjectionService(repository=repository)


HistoryDependency = Annotated[HistoryProjectionService, Depends(get_history_service)]


@router.get(
    "",
    response_model=PlayHistoryResponse,
    summary="Get evidence-qualified Play History",
    description=(
        "Return contribution-safe totals plus separately versioned comparability, grouping, "
        "trend, aggregation, and interpretation decisions for neutral observed-change views."
    ),
)
def get_play_history(
    history: HistoryDependency,
    recent_limit: Annotated[int, Query(ge=1, le=25)] = 5,
) -> PlayHistoryResponse:
    return history.play_history(recent_limit=recent_limit)
