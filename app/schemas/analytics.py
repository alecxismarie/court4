from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

PointTuple = tuple[float, float]


class TimelinePosition(BaseModel):
    model_config = ConfigDict(frozen=True)

    timestamp_seconds: float = Field(ge=0)
    x: float
    y: float


class TimelineReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    analysis_id: str
    selected_player_track_id: int = Field(ge=0)
    observation_count: int = Field(ge=0)
    positions: list[TimelinePosition]
    created_at: datetime


class DistanceMetrics(BaseModel):
    model_config = ConfigDict(frozen=True)

    total_distance_feet: float = Field(ge=0)
    total_distance_meters: float = Field(ge=0)
    average_movement_feet_per_second: float = Field(ge=0)
    average_movement_meters_per_second: float = Field(ge=0)


class ZoneOccupancyMetric(BaseModel):
    model_config = ConfigDict(frozen=True)

    seconds: float = Field(ge=0)
    percentage: float = Field(ge=0, le=100)


class ZoneOccupancyReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    kitchen: ZoneOccupancyMetric
    transition_zone: ZoneOccupancyMetric
    baseline_area: ZoneOccupancyMetric
    tracked_time_seconds: float = Field(ge=0)


class AnalyticsArtifacts(BaseModel):
    model_config = ConfigDict(frozen=True)

    analytics_json: str
    movement_summary_json: str
    timeline_json: str
    trajectory_png: str
    heatmap_png: str


class MovementSummaryReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    analysis_id: str
    selected_player_track_id: int = Field(ge=0)
    match_duration_seconds: float = Field(ge=0)
    tracked_duration_seconds: float = Field(ge=0)
    total_processed_observations: int = Field(ge=0)
    valid_court_observation_count: int = Field(ge=0)
    total_distance_feet: float = Field(ge=0)
    total_distance_meters: float = Field(ge=0)
    average_court_position: PointTuple | None
    average_movement_feet_per_second: float = Field(ge=0)
    average_movement_meters_per_second: float = Field(ge=0)
    zone_occupancy: ZoneOccupancyReport
    created_at: datetime


class AnalyticsReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    analysis_id: str
    source_tracking_report: str
    source_observations: str
    calibration_id: str
    selected_player_track_id: int = Field(ge=0)
    distance: DistanceMetrics
    timeline_observation_count: int = Field(ge=0)
    average_court_position: PointTuple | None
    zone_occupancy: ZoneOccupancyReport
    artifacts: AnalyticsArtifacts
    created_at: datetime
