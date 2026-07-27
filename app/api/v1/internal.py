from typing import Annotated

from fastapi import APIRouter, Depends

from app.config import get_settings
from app.config.settings import Settings
from app.schemas.calibration_readiness import CalibrationReadinessSummary
from app.services.calibration_readiness import CalibrationReadinessService

router = APIRouter(prefix="/internal", tags=["internal-development"])

SettingsDependency = Annotated[Settings, Depends(get_settings)]


def get_readiness_service(settings: SettingsDependency) -> CalibrationReadinessService:
    return CalibrationReadinessService(
        manifest_path=settings.calibration_readiness_manifest_path,
        results_path=settings.calibration_readiness_results_path,
        calibration_report_path=settings.calibration_readiness_report_path,
        disagreements_report_path=settings.calibration_readiness_disagreements_path,
        integrity_path=settings.calibration_readiness_integrity_path,
        governance_path=settings.calibration_readiness_governance_path,
    )


ReadinessServiceDependency = Annotated[
    CalibrationReadinessService,
    Depends(get_readiness_service),
]


@router.get(
    "/calibration-readiness",
    response_model=CalibrationReadinessSummary,
    summary="Get internal calibration readiness",
    description=(
        "Read-only development endpoint over persisted calibration sources. It never "
        "runs inference or changes manifests, reviewer labels, policies, or analytics."
    ),
)
def get_calibration_readiness(
    service: ReadinessServiceDependency,
) -> CalibrationReadinessSummary:
    return service.get_summary()
