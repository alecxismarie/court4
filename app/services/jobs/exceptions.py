from dataclasses import dataclass


@dataclass(frozen=True)
class JobWorkflowError(Exception):
    code: str
    message: str
    status_code: int


class JobRequestError(JobWorkflowError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code=code, message=message, status_code=400)


class JobNotFoundError(JobWorkflowError):
    def __init__(self, message: str = "Analysis not found.") -> None:
        super().__init__(code="analysis_not_found", message=message, status_code=404)


class JobConflictError(JobWorkflowError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code=code, message=message, status_code=409)


class JobTooLargeError(JobWorkflowError):
    def __init__(self, message: str) -> None:
        super().__init__(code="upload_too_large", message=message, status_code=413)


class JobInternalError(JobWorkflowError):
    def __init__(self, message: str = "Unexpected analysis workflow failure.") -> None:
        super().__init__(code="internal_error", message=message, status_code=500)
