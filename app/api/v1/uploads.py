from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Response

from app.auth import VerifiedUser
from app.config import get_settings
from app.config.settings import Settings
from app.schemas.jobs import ApiErrorResponse
from app.schemas.uploads import (
    CompleteUploadRequest,
    InitiateUploadRequest,
    InitiateUploadResponse,
    ResumeUploadRequest,
    UploadPartUrlRequest,
    UploadPartUrlResponse,
    UploadRecoveryResponse,
    UploadSessionResponse,
)
from app.services.uploads import DirectUploadService

router = APIRouter(prefix="/uploads", tags=["uploads"])

ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": ApiErrorResponse, "description": "Invalid upload metadata."},
    401: {"model": ApiErrorResponse, "description": "Authentication is required."},
    404: {"model": ApiErrorResponse, "description": "Upload session was not found."},
    409: {"model": ApiErrorResponse, "description": "Upload state conflict."},
    413: {"model": ApiErrorResponse, "description": "Upload exceeds the application limit."},
    429: {"model": ApiErrorResponse, "description": "Upload concurrency is currently busy."},
    503: {"model": ApiErrorResponse, "description": "Private object storage is unavailable."},
}

SettingsDependency = Annotated[Settings, Depends(get_settings)]


def get_upload_service(settings: SettingsDependency) -> DirectUploadService:
    return DirectUploadService(settings=settings)


UploadServiceDependency = Annotated[DirectUploadService, Depends(get_upload_service)]


@router.post(
    "/initiate",
    response_model=InitiateUploadResponse,
    status_code=201,
    responses=ERROR_RESPONSES,
    summary="Initiate a direct multipart video upload",
)
def initiate_upload(
    request: InitiateUploadRequest,
    user: VerifiedUser,
    service: UploadServiceDependency,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> InitiateUploadResponse:
    return service.initiate(
        owner_user_id=user.id,
        request=request,
        idempotency_key=idempotency_key,
    )


@router.get("/recoverable", response_model=list[UploadRecoveryResponse], responses=ERROR_RESPONSES)
def discover_uploads(
    user: VerifiedUser, service: UploadServiceDependency, response: Response
) -> list[UploadRecoveryResponse]:
    response.headers["Cache-Control"] = "no-store"
    return service.discover(owner_user_id=user.id)


@router.get(
    "/{upload_session_id}/recovery",
    response_model=UploadRecoveryResponse,
    responses=ERROR_RESPONSES,
)
def recover_upload(
    upload_session_id: UUID,
    user: VerifiedUser,
    service: UploadServiceDependency,
    response: Response,
) -> UploadRecoveryResponse:
    response.headers["Cache-Control"] = "no-store"
    return service.recovery(owner_user_id=user.id, upload_session_id=upload_session_id)


@router.post(
    "/{upload_session_id}/resume", response_model=UploadRecoveryResponse, responses=ERROR_RESPONSES
)
def resume_upload(
    upload_session_id: UUID,
    request: ResumeUploadRequest,
    user: VerifiedUser,
    service: UploadServiceDependency,
    response: Response,
) -> UploadRecoveryResponse:
    response.headers["Cache-Control"] = "no-store"
    return service.recovery(
        owner_user_id=user.id, upload_session_id=upload_session_id, resume=request
    )


@router.get(
    "/{upload_session_id}",
    response_model=UploadSessionResponse,
    responses=ERROR_RESPONSES,
    summary="Get direct upload state",
)
def get_upload(
    upload_session_id: UUID,
    background_tasks: BackgroundTasks,
    user: VerifiedUser,
    service: UploadServiceDependency,
) -> UploadSessionResponse:
    result = service.get(owner_user_id=user.id, upload_session_id=upload_session_id)
    if result.status in {"verifying", "analyzing"}:
        background_tasks.add_task(service.verify_and_analyze, upload_session_id)
    return result


@router.post(
    "/{upload_session_id}/parts",
    response_model=UploadPartUrlResponse,
    responses=ERROR_RESPONSES,
    summary="Refresh narrowly scoped multipart part URLs",
)
def create_part_urls(
    upload_session_id: UUID,
    request: UploadPartUrlRequest,
    user: VerifiedUser,
    service: UploadServiceDependency,
) -> UploadPartUrlResponse:
    return service.create_part_urls(
        owner_user_id=user.id,
        upload_session_id=upload_session_id,
        part_numbers=request.part_numbers,
    )


@router.post(
    "/{upload_session_id}/complete",
    response_model=UploadSessionResponse,
    status_code=202,
    responses=ERROR_RESPONSES,
    summary="Complete and verify a direct multipart upload",
)
def complete_upload(
    upload_session_id: UUID,
    request: CompleteUploadRequest,
    background_tasks: BackgroundTasks,
    user: VerifiedUser,
    service: UploadServiceDependency,
    response: Response,
) -> UploadSessionResponse:
    result = service.complete(
        owner_user_id=user.id,
        upload_session_id=upload_session_id,
        request=request,
    )
    if result.status in {"verifying", "analyzing"}:
        background_tasks.add_task(service.verify_and_analyze, upload_session_id)
    elif result.status == "completed":
        response.status_code = 200
    return result


@router.delete(
    "/{upload_session_id}",
    response_model=UploadSessionResponse,
    responses=ERROR_RESPONSES,
    summary="Abort a direct multipart upload",
)
def abort_upload(
    upload_session_id: UUID,
    user: VerifiedUser,
    service: UploadServiceDependency,
) -> UploadSessionResponse:
    return service.abort(owner_user_id=user.id, upload_session_id=upload_session_id)
