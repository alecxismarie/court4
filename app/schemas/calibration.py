from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

PointTuple = tuple[float, float]


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
