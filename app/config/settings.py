from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import (
    AliasChoices,
    Field,
    PositiveFloat,
    PositiveInt,
    ValidationInfo,
    field_validator,
)
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="PICKLEBALL_AI_",
        case_sensitive=False,
    )

    input_dir: Path = Path("data/input")
    output_dir: Path = Path("data/output")
    default_sample_interval_seconds: PositiveFloat = Field(default=30)
    max_upload_size_bytes: PositiveInt = Field(default=1_073_741_824)
    supported_extensions: Annotated[tuple[str, ...], NoDecode] = (
        ".mp4",
        ".mov",
        ".avi",
        ".mkv",
    )
    logging_level: str = "INFO"
    calibration_output_dir: Path = Path("data/output")
    calibration_top_down_width_pixels: PositiveInt = Field(default=1000)
    numeric_validation_tolerance: PositiveFloat = Field(default=0.000001)
    min_calibration_polygon_area_pixels: PositiveFloat = Field(default=1000)
    transition_area_depth_feet: PositiveFloat = Field(default=8)
    tracking_output_dir: Path = Path("data/output")
    detector_model_path: Path = Field(
        default=Path("models/yolo11n.pt"),
        validation_alias=AliasChoices(
            "COURT4_DETECTOR_MODEL_PATH",
            "PICKLEBALL_AI_DETECTOR_MODEL_PATH",
        ),
    )
    detector_confidence_threshold: float = Field(default=0.35, ge=0, le=1)
    detector_image_size: PositiveInt = Field(default=640)
    frame_processing_interval: PositiveInt = Field(default=1)
    court_inclusion_margin_feet: float = Field(default=3, ge=0)
    min_eligible_track_duration_seconds: float = Field(default=1, ge=0)
    min_eligible_observation_count: PositiveInt = Field(default=3)
    min_eligible_inside_court_ratio: float = Field(default=0.6, ge=0, le=1)
    min_eligible_inside_extended_ratio: float = Field(default=0.6, ge=0, le=1)
    min_eligible_court_movement_rate_feet_per_second: float = Field(default=1.2, ge=0)
    max_selectable_player_tracks: PositiveInt = Field(default=4)
    min_eligible_average_confidence: float = Field(default=0.4, ge=0, le=1)
    annotated_video_codec: str = "mp4v"
    annotated_video_fps: PositiveFloat = Field(default=10)
    analytics_output_dir: Path = Path("data/output")
    analytics_image_width_pixels: PositiveInt = Field(default=1000)
    api_base_path: str = "/api/v1"
    analysis_output_dir: Path = Path("data/output")
    upload_chunk_size_bytes: PositiveInt = Field(default=1_048_576)
    default_tracking_backend: str = "controlled-json"
    court_detection_calibration_id: str = "auto-court-detection"
    court_detection_min_confidence: float = Field(default=0.72, ge=0, le=1)
    court_detection_low_confidence_threshold: float = Field(default=0.25, ge=0, le=1)
    frontend_allowed_origins: Annotated[tuple[str, ...], NoDecode] = (
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    )

    @field_validator("supported_extensions", mode="before")
    @classmethod
    def parse_supported_extensions(cls, value: object) -> object:
        if isinstance(value, str):
            return tuple(item.strip() for item in value.split(",") if item.strip())
        return value

    @field_validator("supported_extensions")
    @classmethod
    def normalize_supported_extensions(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = []
        for extension in value:
            cleaned = extension.strip().lower()
            if not cleaned:
                continue
            normalized.append(cleaned if cleaned.startswith(".") else f".{cleaned}")
        if not normalized:
            raise ValueError("At least one supported video extension is required.")
        return tuple(dict.fromkeys(normalized))

    @field_validator("logging_level")
    @classmethod
    def normalize_logging_level(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if not cleaned:
            raise ValueError("Logging level cannot be empty.")
        return cleaned

    @field_validator("annotated_video_codec")
    @classmethod
    def normalize_annotated_video_codec(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) != 4:
            raise ValueError("Annotated video codec must be exactly four characters.")
        return cleaned

    @field_validator("api_base_path")
    @classmethod
    def normalize_api_base_path(cls, value: str) -> str:
        cleaned = value.strip().rstrip("/")
        if not cleaned.startswith("/"):
            cleaned = f"/{cleaned}"
        if cleaned == "/":
            raise ValueError("API base path cannot be root.")
        return cleaned

    @field_validator("default_tracking_backend")
    @classmethod
    def normalize_default_tracking_backend(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if cleaned not in {"controlled-json", "ultralytics"}:
            raise ValueError("Default tracking backend must be controlled-json or ultralytics.")
        return cleaned

    @field_validator("court_detection_calibration_id")
    @classmethod
    def normalize_court_detection_calibration_id(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Court detection calibration ID cannot be empty.")
        if cleaned in {".", ".."} or "/" in cleaned or "\\" in cleaned:
            raise ValueError("Court detection calibration ID must not contain path separators.")
        return cleaned

    @field_validator("frontend_allowed_origins", mode="before")
    @classmethod
    def parse_frontend_allowed_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return tuple(item.strip() for item in value.split(",") if item.strip())
        return value

    @field_validator("court_detection_low_confidence_threshold")
    @classmethod
    def validate_court_detection_threshold_order(cls, value: float, info: ValidationInfo) -> float:
        min_confidence = info.data.get("court_detection_min_confidence")
        if isinstance(min_confidence, float | int) and value > min_confidence:
            raise ValueError(
                "Court detection low-confidence threshold cannot exceed min confidence."
            )
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
