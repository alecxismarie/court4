from collections.abc import Callable
from functools import wraps
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from app.services.jobs.workflow import AnalysisWorkflowService

Result = TypeVar("Result")


def media_operation(
    *, require_source: bool = True
) -> Callable[[Callable[..., Result]], Callable[..., Result]]:
    """Keep deletion outside an in-flight workflow operation, including workspace writes."""

    def decorate(method: Callable[..., Result]) -> Callable[..., Result]:
        @wraps(method)
        def guarded(
            self: "AnalysisWorkflowService", analysis_id: str, *args: Any, **kwargs: Any
        ) -> Result:
            with self.repository.media_operation(analysis_id):
                if require_source:
                    self.repository.require_retained_source(analysis_id)
                return method(self, analysis_id, *args, **kwargs)

        return guarded

    return decorate
