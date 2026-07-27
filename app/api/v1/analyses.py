from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse

from app.config import get_settings
from app.config.settings import Settings
from app.schemas.active_play import ActivePlayReport
from app.schemas.jobs import (
    AnalysisJobResponse,
    AnalyticsGenerationResponse,
    AnalyticsResponse,
    ApiErrorResponse,
    CalibrationRequest,
    CalibrationResponse,
    CourtDetectionResponse,
    PlayerSelectionRequest,
    PlayerSelectionResponse,
    PlayersResponse,
    SampledFramesResponse,
    TrackingRequest,
    TrackingResponse,
    UploadVideoResponse,
)
from app.schemas.player_candidates import (
    CandidateMergeRequest,
    CandidateRejectRequest,
    CandidateUnmergeRequest,
    PlayerCandidateCollection,
)
from app.services.jobs import AnalysisWorkflowService

router = APIRouter(prefix="/analyses", tags=["analyses"])

ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": ApiErrorResponse, "description": "Invalid request."},
    404: {"model": ApiErrorResponse, "description": "Analysis or artifact not found."},
    409: {"model": ApiErrorResponse, "description": "Workflow step is not ready."},
    413: {"model": ApiErrorResponse, "description": "Upload exceeds configured size limit."},
}


SettingsDependency = Annotated[Settings, Depends(get_settings)]
VideoUploadFile = Annotated[UploadFile, File(description="Pickleball match video file.")]


def get_workflow_service(settings: SettingsDependency) -> AnalysisWorkflowService:
    return AnalysisWorkflowService(settings=settings)


WorkflowDependency = Annotated[AnalysisWorkflowService, Depends(get_workflow_service)]


@router.post(
    "",
    response_model=UploadVideoResponse,
    status_code=201,
    summary="Upload a match video",
    description=(
        "Upload a pickleball match video, create a filesystem-backed analysis job, "
        "and run synchronous video inspection."
    ),
    responses=ERROR_RESPONSES,
)
async def upload_video(
    file: VideoUploadFile,
    workflow: WorkflowDependency,
) -> UploadVideoResponse:
    return await workflow.create_analysis(file)


@router.get(
    "/{analysis_id}",
    response_model=AnalysisJobResponse,
    summary="Get analysis job",
    description=(
        "Return persisted analysis job state, stage flags, timestamps, errors, "
        "and available artifacts."
    ),
    responses=ERROR_RESPONSES,
)
def get_analysis(
    analysis_id: str,
    workflow: WorkflowDependency,
) -> AnalysisJobResponse:
    return workflow.get_job(analysis_id)


@router.get(
    "/{analysis_id}/frames",
    response_model=SampledFramesResponse,
    summary="List sampled frames",
    description="List sampled inspection frames and API artifact URLs for one analysis.",
    responses=ERROR_RESPONSES,
)
def list_sampled_frames(
    analysis_id: str,
    workflow: WorkflowDependency,
) -> SampledFramesResponse:
    return workflow.list_sampled_frames(analysis_id)


@router.get(
    "/{analysis_id}/artifacts/{artifact_path:path}",
    summary="Retrieve analysis artifact",
    description="Serve a generated artifact from within the requested analysis directory.",
    responses=ERROR_RESPONSES,
)
def retrieve_artifact(
    analysis_id: str,
    artifact_path: str,
    workflow: WorkflowDependency,
) -> FileResponse:
    artifact = workflow.get_artifact_file(analysis_id, artifact_path)
    content_disposition_type = (
        "inline" if artifact.content_type.startswith("image/") else "attachment"
    )
    return FileResponse(
        artifact.path,
        media_type=artifact.content_type,
        filename=artifact.path.name,
        content_disposition_type=content_disposition_type,
    )


@router.post(
    "/{analysis_id}/calibration",
    response_model=CalibrationResponse,
    summary="Submit court calibration",
    description=(
        "Create a manual court calibration from one sampled frame and four ordered court corners."
    ),
    responses=ERROR_RESPONSES,
)
def submit_calibration(
    analysis_id: str,
    request: CalibrationRequest,
    workflow: WorkflowDependency,
) -> CalibrationResponse:
    return workflow.submit_calibration(analysis_id, request)


@router.post(
    "/{analysis_id}/court-detection",
    response_model=CourtDetectionResponse,
    summary="Detect court automatically",
    description=(
        "Attempt automatic pickleball court detection from sampled frames and save "
        "calibration artifacts when confidence is high enough."
    ),
    responses=ERROR_RESPONSES,
)
def detect_court(
    analysis_id: str,
    workflow: WorkflowDependency,
) -> CourtDetectionResponse:
    return workflow.detect_court(analysis_id)


@router.post(
    "/{analysis_id}/tracking",
    response_model=TrackingResponse,
    summary="Start player tracking",
    description=(
        "Run player tracking using a controlled JSONL backend or the optional Ultralytics backend."
    ),
    responses=ERROR_RESPONSES,
)
def start_tracking(
    analysis_id: str,
    request: TrackingRequest,
    workflow: WorkflowDependency,
) -> TrackingResponse:
    return workflow.start_tracking(analysis_id, request)


@router.get(
    "/{analysis_id}/player-candidates",
    response_model=PlayerCandidateCollection,
    summary="List stable player candidates",
    description="Return ranked player candidates, review state, previews, and suitability.",
    responses=ERROR_RESPONSES,
)
def list_player_candidates(
    analysis_id: str,
    workflow: WorkflowDependency,
) -> PlayerCandidateCollection:
    return workflow.list_player_candidates(analysis_id)


@router.post(
    "/{analysis_id}/player-candidates/generate",
    response_model=PlayerCandidateCollection,
    summary="Generate stable player candidates",
    description="Deterministically regenerate candidates while preserving compatible review state.",
    responses=ERROR_RESPONSES,
)
def generate_player_candidates(
    analysis_id: str,
    workflow: WorkflowDependency,
) -> PlayerCandidateCollection:
    return workflow.generate_player_candidates(analysis_id)


@router.post(
    "/{analysis_id}/player-candidates/{candidate_id}/select",
    response_model=PlayerCandidateCollection,
    summary="Select a player candidate",
    responses=ERROR_RESPONSES,
)
def select_player_candidate(
    analysis_id: str,
    candidate_id: str,
    workflow: WorkflowDependency,
) -> PlayerCandidateCollection:
    return workflow.select_player_candidate(analysis_id, candidate_id)


@router.post(
    "/{analysis_id}/player-candidates/{candidate_id}/reject",
    response_model=PlayerCandidateCollection,
    summary="Exclude a candidate from player selection",
    responses=ERROR_RESPONSES,
)
def reject_player_candidate(
    analysis_id: str,
    candidate_id: str,
    request: CandidateRejectRequest,
    workflow: WorkflowDependency,
) -> PlayerCandidateCollection:
    return workflow.reject_player_candidate(analysis_id, candidate_id, request.reason)


@router.post(
    "/{analysis_id}/player-candidates/{candidate_id}/restore",
    response_model=PlayerCandidateCollection,
    summary="Restore an excluded player candidate",
    responses=ERROR_RESPONSES,
)
def restore_player_candidate(
    analysis_id: str,
    candidate_id: str,
    workflow: WorkflowDependency,
) -> PlayerCandidateCollection:
    return workflow.restore_player_candidate(analysis_id, candidate_id)


@router.post(
    "/{analysis_id}/player-candidates/merge",
    response_model=PlayerCandidateCollection,
    summary="Manually merge two player candidates",
    responses=ERROR_RESPONSES,
)
def merge_player_candidates(
    analysis_id: str,
    request: CandidateMergeRequest,
    workflow: WorkflowDependency,
) -> PlayerCandidateCollection:
    return workflow.merge_player_candidates(analysis_id, request.candidate_ids)


@router.post(
    "/{analysis_id}/player-candidates/unmerge",
    response_model=PlayerCandidateCollection,
    summary="Undo a manual candidate merge",
    responses=ERROR_RESPONSES,
)
def unmerge_player_candidates(
    analysis_id: str,
    request: CandidateUnmergeRequest,
    workflow: WorkflowDependency,
) -> PlayerCandidateCollection:
    return workflow.unmerge_player_candidates(analysis_id, request.candidate_id)


@router.get(
    "/{analysis_id}/players",
    response_model=PlayersResponse,
    summary="List eligible player tracks",
    description=(
        "Return track summaries, eligibility flags, rejection reasons, and selected-player state."
    ),
    responses=ERROR_RESPONSES,
)
def list_players(
    analysis_id: str,
    workflow: WorkflowDependency,
) -> PlayersResponse:
    return workflow.list_players(analysis_id)


@router.post(
    "/{analysis_id}/players/select",
    response_model=PlayerSelectionResponse,
    summary="Select player track",
    description="Select one eligible tracked player for analytics.",
    responses=ERROR_RESPONSES,
)
def select_player(
    analysis_id: str,
    request: PlayerSelectionRequest,
    workflow: WorkflowDependency,
) -> PlayerSelectionResponse:
    return workflow.select_player(analysis_id, request)


@router.post(
    "/{analysis_id}/analytics",
    response_model=AnalyticsGenerationResponse,
    summary="Generate movement analytics",
    description="Generate selected-player movement analytics and top-down images.",
    responses=ERROR_RESPONSES,
)
def generate_analytics(
    analysis_id: str,
    workflow: WorkflowDependency,
) -> AnalyticsGenerationResponse:
    return workflow.generate_analytics(analysis_id)


@router.get(
    "/{analysis_id}/analytics",
    response_model=AnalyticsResponse,
    summary="Get movement analytics",
    description="Return the generated analytics report after analytics have been created.",
    responses=ERROR_RESPONSES,
)
def get_analytics(
    analysis_id: str,
    workflow: WorkflowDependency,
) -> AnalyticsResponse:
    return workflow.get_analytics(analysis_id)


@router.post(
    "/{analysis_id}/debug/active-play",
    response_model=ActivePlayReport,
    summary="Generate shadow Active Play evidence",
    description=(
        "Internal debug-only shadow output. This does not alter analytics, Match IQ, "
        "cards, dashboards, or the normal player workflow."
    ),
    responses=ERROR_RESPONSES,
    tags=["internal-debug"],
)
def generate_active_play(
    analysis_id: str,
    workflow: WorkflowDependency,
) -> ActivePlayReport:
    return workflow.generate_active_play(analysis_id)


@router.get(
    "/{analysis_id}/debug/active-play",
    response_model=ActivePlayReport,
    summary="Get shadow Active Play evidence",
    description="Return an existing internal shadow Active Play artifact.",
    responses=ERROR_RESPONSES,
    tags=["internal-debug"],
)
def get_active_play(
    analysis_id: str,
    workflow: WorkflowDependency,
) -> ActivePlayReport:
    return workflow.get_active_play(analysis_id)
