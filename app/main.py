import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.api.v1 import router as api_v1_router
from app.auth.errors import AuthenticationError
from app.config import get_settings
from app.core.logging import configure_logging
from app.schemas.jobs import ApiErrorDetail, ApiErrorResponse
from app.services.jobs import JobWorkflowError

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.logging_level)

    application = FastAPI(
        title="Court4",
        description="Upload-first pickleball performance analytics API.",
        version="0.5.0",
    )
    application.include_router(router)
    application.include_router(api_v1_router, prefix=settings.api_base_path)
    if settings.frontend_allowed_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.frontend_allowed_origins),
            allow_credentials=True,
            allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
            allow_headers=["*"],
        )
    application.add_exception_handler(JobWorkflowError, _job_workflow_error_handler)
    application.add_exception_handler(AuthenticationError, _authentication_error_handler)
    application.add_exception_handler(Exception, _unexpected_error_handler)
    return application


async def _job_workflow_error_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    del request
    if not isinstance(exc, JobWorkflowError):
        return _internal_error_response()
    response = ApiErrorResponse(error=ApiErrorDetail(code=exc.code, message=exc.message))
    return JSONResponse(status_code=exc.status_code, content=response.model_dump(mode="json"))


async def _unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "api_unexpected_error",
        extra={"path": request.url.path, "method": request.method},
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return _internal_error_response()


async def _authentication_error_handler(request: Request, exc: Exception) -> JSONResponse:
    del request
    if not isinstance(exc, AuthenticationError):
        return _internal_error_response()
    response = ApiErrorResponse(error=ApiErrorDetail(code=exc.code, message=exc.message))
    return JSONResponse(status_code=exc.status_code, content=response.model_dump(mode="json"))


def _internal_error_response() -> JSONResponse:
    response = ApiErrorResponse(
        error=ApiErrorDetail(code="internal_error", message="Unexpected internal server error.")
    )
    return JSONResponse(status_code=500, content=response.model_dump(mode="json"))


app = create_app()
