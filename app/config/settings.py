from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlparse
from uuid import UUID

from pydantic import (
    AliasChoices,
    Field,
    PositiveFloat,
    PositiveInt,
    SecretStr,
    ValidationInfo,
    field_validator,
    model_validator,
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
    environment: Literal["development", "test", "staging", "production"] = "development"
    persistence_backend: Literal["postgresql"] = "postgresql"
    database_url: str = (
        "postgresql+psycopg://court4:court4_local_only@127.0.0.1:55433/court4"
    )
    database_pool_size: PositiveInt = 10
    database_max_overflow: int = Field(default=10, ge=0)
    database_pool_timeout_seconds: PositiveInt = 10
    database_pool_recycle_seconds: PositiveInt = 1800
    database_pool_pre_ping: bool = True
    database_statement_timeout_ms: PositiveInt = 10_000
    database_lock_timeout_ms: PositiveInt = 5_000
    database_idle_transaction_timeout_ms: PositiveInt = 15_000
    local_storage_root: Path = Path("data/output")
    bootstrap_user_enabled: bool = False
    bootstrap_user_id: UUID | None = None
    bootstrap_user_identity: str | None = None
    legacy_import_enabled: bool = False
    pipeline_version: str = "court4-1.8b"
    persistence_schema_version: PositiveInt = 1
    policy_version: str = "phase-1.8b"
    software_commit_identifier: str = "working-tree"
    deployment_build_identifier: str = "local"
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
    calibration_readiness_manifest_path: Path = Path("calibration/manifest.v2.json")
    calibration_readiness_results_path: Path = Path("calibration-results.json")
    calibration_readiness_report_path: Path = Path("CALIBRATION_REPORT.md")
    calibration_readiness_disagreements_path: Path = Path("CALIBRATION_DISAGREEMENTS.md")
    calibration_readiness_integrity_path: Path = Path("calibration-readiness-integrity.json")
    calibration_readiness_governance_path: Path = Path("calibration/readiness-governance.json")
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
    auth_access_token_secret: SecretStr = SecretStr(
        "development-only-change-this-secret-before-production"
    )
    auth_access_token_minutes: PositiveInt = 10
    auth_refresh_token_days: PositiveInt = 30
    auth_token_issuer: str = "court4"
    auth_token_audience: str = "court4-web"
    auth_refresh_cookie_name: str = "court4_refresh"
    auth_cookie_secure: bool | None = None
    auth_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    auth_min_password_length: int = Field(default=12, ge=8, le=128)
    auth_max_password_length: int = Field(default=256, ge=64, le=1024)
    auth_rate_limit_window_seconds: PositiveInt = 60
    auth_register_rate_limit: PositiveInt = 5
    auth_login_rate_limit: PositiveInt = 10
    auth_refresh_rate_limit: PositiveInt = 30
    auth_frontend_base_url: str = "http://localhost:3000"
    auth_email_backend: Literal["development", "provider"] = "development"
    auth_development_email_sink_enabled: bool = True
    auth_verification_token_hours: PositiveInt = 24
    auth_password_reset_token_minutes: PositiveInt = 45
    auth_resend_verification_rate_limit: PositiveInt = 3
    auth_forgot_password_rate_limit: PositiveInt = 5
    auth_reset_password_rate_limit: PositiveInt = 10
    auth_change_password_rate_limit: PositiveInt = 5
    auth_session_action_rate_limit: PositiveInt = 10

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

    @field_validator("frontend_allowed_origins")
    @classmethod
    def validate_frontend_allowed_origins(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(origin == "*" for origin in value):
            raise ValueError("Credentialed CORS does not permit a wildcard origin.")
        return tuple(dict.fromkeys(origin.rstrip("/") for origin in value))

    @field_validator("auth_access_token_secret")
    @classmethod
    def validate_auth_secret(cls, value: SecretStr, info: ValidationInfo) -> SecretStr:
        secret = value.get_secret_value()
        if len(secret) < 32:
            raise ValueError("Access-token secret must contain at least 32 characters.")
        if (
            info.data.get("environment") in {"staging", "production"}
            and secret == "development-only-change-this-secret-before-production"
        ):
            raise ValueError("A deployment-specific access-token secret is required.")
        return value

    @field_validator("auth_frontend_base_url")
    @classmethod
    def validate_auth_frontend_base_url(cls, value: str) -> str:
        cleaned = value.strip().rstrip("/")
        parsed = urlparse(cleaned)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Frontend base URL must be an absolute HTTP(S) URL.")
        if parsed.query or parsed.fragment or parsed.username or parsed.password:
            raise ValueError("Frontend base URL must not contain credentials, query, or fragment.")
        return cleaned

    @property
    def refresh_cookie_secure(self) -> bool:
        if self.auth_cookie_secure is not None:
            return self.auth_cookie_secure
        return self.environment in {"staging", "production"}

    @model_validator(mode="after")
    def validate_auth_deployment_security(self) -> "Settings":
        if (
            self.environment in {"staging", "production"}
            and self.auth_access_token_secret.get_secret_value()
            == "development-only-change-this-secret-before-production"
        ):
            raise ValueError("A deployment-specific access-token secret is required.")
        if self.auth_cookie_samesite == "none" and not self.refresh_cookie_secure:
            raise ValueError("SameSite=None requires a Secure refresh cookie.")
        if self.environment in {"staging", "production"} and not self.refresh_cookie_secure:
            raise ValueError("Staging and production require a Secure refresh cookie.")
        if (
            self.environment in {"staging", "production"}
            and self.auth_email_backend == "development"
        ):
            raise ValueError("The development email sink cannot be used in a deployment.")
        if (
            self.environment in {"staging", "production"}
            and self.auth_development_email_sink_enabled
        ):
            raise ValueError("The development email sink must be disabled in a deployment.")
        if self.environment in {
            "staging",
            "production",
        } and not self.auth_frontend_base_url.startswith("https://"):
            raise ValueError("Deployment frontend links must use HTTPS.")
        return self

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
