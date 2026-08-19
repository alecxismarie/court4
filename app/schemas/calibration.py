from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

PointTuple = tuple[float, float]


class CalibrationGenerationState(StrEnum):
    calibration_generated = "calibration_generated"


class CalibrationVerificationState(StrEnum):
    unverified = "unverified"
    verified = "verified"
    rejected = "rejected"


class CourtProjectionAvailability(StrEnum):
    unavailable = "unavailable"
    approximate_court_plane_projection = "approximate_court_plane_projection"


class CalibrationVerificationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(default=1, ge=1)
    calibration_id: str
    calibration_checksum_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    verification_state: CalibrationVerificationState
    verified_at: datetime
    verification_method: str
    reviewer_context: str | None = None


class CalibrationCoordinateSystem(BaseModel):
    model_config = ConfigDict(frozen=True)

    unit: str
    origin: str
    x_axis: str
    y_axis: str


class CalibrationCourtDimensions(BaseModel):
    model_config = ConfigDict(frozen=True)

    width: float = Field(gt=0)
    length: float = Field(gt=0)
    non_volley_zone_depth: float = Field(gt=0)


class OrderedCalibrationPoints(BaseModel):
    model_config = ConfigDict(frozen=True)

    near_left: PointTuple
    near_right: PointTuple
    far_right: PointTuple
    far_left: PointTuple


class CourtCalibrationReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: int = Field(default=1, ge=1)
    generation_state: CalibrationGenerationState = CalibrationGenerationState.calibration_generated
    calibration_id: str
    source_image: str
    image_width: int = Field(gt=0)
    image_height: int = Field(gt=0)
    coordinate_system: CalibrationCoordinateSystem
    court_dimensions: CalibrationCourtDimensions
    image_points: OrderedCalibrationPoints
    court_points: OrderedCalibrationPoints
    image_to_court_matrix: list[list[float]]
    court_to_image_matrix: list[list[float]]
    reprojection_error: float = Field(ge=0)
    round_trip_error: float = Field(ge=0)
    top_down_image: str | None = None
    created_at: datetime


def court_projection_availability(
    calibration: CourtCalibrationReport | None,
    verification: CalibrationVerificationRecord | None,
    *,
    calibration_checksum_sha256: str | None,
) -> CourtProjectionAvailability:
    """Only checksum-bound human verification permits an approximate plane projection."""
    if calibration is None or verification is None or calibration_checksum_sha256 is None:
        return CourtProjectionAvailability.unavailable
    if verification.verification_state != CalibrationVerificationState.verified:
        return CourtProjectionAvailability.unavailable
    if verification.calibration_id != calibration.calibration_id:
        return CourtProjectionAvailability.unavailable
    if verification.calibration_checksum_sha256 != calibration_checksum_sha256:
        return CourtProjectionAvailability.unavailable
    return CourtProjectionAvailability.approximate_court_plane_projection
