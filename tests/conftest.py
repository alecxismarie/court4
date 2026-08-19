import os
from collections.abc import Callable
from pathlib import Path
from typing import cast

import cv2
import numpy as np
import pytest

os.environ["PICKLEBALL_AI_ENVIRONMENT"] = "test"
# Fail independently of a developer's root .env: automated tests use only the
# isolated in-memory development sink unless a single test opts in explicitly.
os.environ["EMAIL_PROVIDER"] = "development"
os.environ["ALLOW_EXTERNAL_EMAIL_IN_TESTS"] = "false"
os.environ["PICKLEBALL_AI_AUTH_DEVELOPMENT_EMAIL_SINK_ENABLED"] = "true"
# Override any shell/root values before Settings can read .env. Provider tests pass
# isolated fake credentials directly and mock their transports.
os.environ["BREVO_API_KEY"] = ""
os.environ["RESEND_API_KEY"] = ""
os.environ.setdefault("PICKLEBALL_AI_PERSISTENCE_BACKEND", "postgresql")
os.environ["PICKLEBALL_AI_DATABASE_URL"] = os.environ.get(
    "COURT4_TEST_DATABASE_URL",
    "postgresql+psycopg://court4_test:court4_test_local_only@localhost:55434/court4_test",
)
os.environ["PICKLEBALL_AI_ALLOW_DESTRUCTIVE_DATABASE_OPERATIONS"] = "true"
os.environ["PICKLEBALL_AI_EXPECTED_TEST_DATABASE_PREFIX"] = os.environ.get(
    "COURT4_TEST_EXPECTED_DATABASE_PREFIX", "court4_test"
)
os.environ["PICKLEBALL_AI_EXPECTED_TEST_DATABASE_HOST"] = os.environ.get(
    "COURT4_TEST_EXPECTED_DATABASE_HOST", "localhost"
)
os.environ["PICKLEBALL_AI_EXPECTED_TEST_DATABASE_USER"] = os.environ.get(
    "COURT4_TEST_EXPECTED_DATABASE_USER", "court4_test"
)
os.environ.setdefault("PICKLEBALL_AI_BOOTSTRAP_USER_ENABLED", "true")
os.environ.setdefault("PICKLEBALL_AI_BOOTSTRAP_USER_ID", "00000000-0000-4000-8000-000000000002")
os.environ.setdefault("PICKLEBALL_AI_BOOTSTRAP_USER_IDENTITY", "test-suite@court4.invalid")


def pytest_sessionstart(session: pytest.Session) -> None:
    del session
    from alembic import command
    from alembic.config import Config

    from app.config import get_settings
    from app.persistence.database_safety import (
        ExpectedDatabaseIdentity,
        assert_isolated_test_database_url,
    )

    settings = get_settings()
    assert_isolated_test_database_url(
        settings.database_url,
        environment=settings.environment,
        expected=ExpectedDatabaseIdentity(
            prefix=settings.expected_test_database_prefix,
            host=settings.expected_test_database_host,
            username=settings.expected_test_database_user,
        ),
    )

    command.upgrade(Config("alembic.ini"), "head")


@pytest.fixture(autouse=True)
def clean_production_database() -> None:
    from sqlalchemy import text

    from app.auth.rate_limit import auth_rate_limiter
    from app.config import get_settings
    from app.email.dependencies import get_development_email_sink
    from app.persistence.bootstrap import configured_bootstrap_identity
    from app.persistence.database_safety import (
        ExpectedDatabaseIdentity,
        assert_destructive_database_operation,
    )
    from app.persistence.runtime import get_persistence

    runtime = get_persistence()
    settings = get_settings()
    assert_destructive_database_operation(
        runtime.engine,
        database_url=settings.database_url,
        environment=settings.environment,
        allow_destructive_operations=settings.allow_destructive_database_operations,
        expected=ExpectedDatabaseIdentity(
            prefix=settings.expected_test_database_prefix,
            host=settings.expected_test_database_host,
            username=settings.expected_test_database_user,
        ),
        operation="pytest fixture cleanup",
    )
    with runtime.engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE TABLE account_tokens, refresh_sessions, player_selections, "
                "calibration_verifications, analysis_artifacts, analysis_stage_executions, "
                "analysis_state_events, idempotency_records, analysis_runs, "
                "analyses, uploaded_videos, users RESTART IDENTITY CASCADE"
            )
        )
    identity = configured_bootstrap_identity(settings)
    runtime.service.ensure_bootstrap_user(identity)
    auth_rate_limiter.reset()
    get_development_email_sink().clear()


@pytest.fixture
def synthetic_video_factory() -> Callable[..., Path]:
    def create_video(
        path: Path,
        *,
        frame_count: int = 30,
        fps: float = 10.0,
        width: int = 64,
        height: int = 48,
    ) -> Path:
        fourcc = cv2.VideoWriter_fourcc(*"MJPG")  # type: ignore[attr-defined]
        writer = cv2.VideoWriter(str(path), fourcc, fps, (width, height))
        if not writer.isOpened():
            raise RuntimeError("OpenCV could not create the synthetic test video.")

        try:
            for index in range(frame_count):
                frame = np.zeros((height, width, 3), dtype=np.uint8)
                frame[:, :, 0] = (index * 7) % 255
                frame[:, :, 1] = (index * 13) % 255
                frame[:, :, 2] = (index * 19) % 255
                writer.write(frame)
        finally:
            writer.release()

        return path

    return create_video


@pytest.fixture
def synthetic_court_video_factory() -> Callable[..., Path]:
    def create_video(
        path: Path,
        *,
        frame_count: int = 30,
        fps: float = 10.0,
        width: int = 800,
        height: int = 900,
        court_scale: float = 1.0,
    ) -> Path:
        fourcc = cv2.VideoWriter_fourcc(*"MJPG")  # type: ignore[attr-defined]
        writer = cv2.VideoWriter(str(path), fourcc, fps, (width, height))
        if not writer.isOpened():
            raise RuntimeError("OpenCV could not create the synthetic court test video.")

        try:
            for index in range(frame_count):
                frame = _synthetic_court_frame(
                    width=width,
                    height=height,
                    court_scale=court_scale,
                    brightness=245 - (index % 3) * 8,
                )
                writer.write(frame)
        finally:
            writer.release()

        return path

    return create_video


@pytest.fixture
def synthetic_court_image_factory() -> Callable[..., Path]:
    def create_image(
        path: Path,
        *,
        width: int = 800,
        height: int = 900,
    ) -> Path:
        image = np.full((height, width, 3), 245, dtype=np.uint8)
        court_polygon = np.array(
            [(80, 760), (720, 760), (600, 120), (200, 120)],
            dtype=np.int32,
        )
        cv2.polylines(image, [court_polygon], isClosed=True, color=(0, 140, 0), thickness=3)
        cv2.line(image, (140, 440), (660, 440), (0, 0, 255), thickness=2)
        cv2.line(image, (110, 540), (690, 540), (255, 0, 255), thickness=2)
        cv2.line(image, (170, 340), (630, 340), (255, 0, 255), thickness=2)
        if not cv2.imwrite(str(path), image):
            raise RuntimeError("OpenCV could not create the synthetic test court image.")
        return path

    return create_image


def _synthetic_court_frame(
    *,
    width: int,
    height: int,
    court_scale: float,
    brightness: int,
) -> np.ndarray:
    image = np.full((height, width, 3), brightness, dtype=np.uint8)
    base_corners = np.array(
        [
            (0.10 * width, 0.84 * height),
            (0.90 * width, 0.84 * height),
            (0.75 * width, 0.13 * height),
            (0.25 * width, 0.13 * height),
        ],
        dtype=np.float32,
    )
    center = np.array((width / 2.0, height / 2.0), dtype=np.float32)
    corners = center + (base_corners - center) * court_scale
    court_polygon = corners.astype(np.int32)

    cv2.polylines(image, [court_polygon], isClosed=True, color=(0, 140, 0), thickness=3)
    for first, second, color in (
        (
            _interpolate(corners[0], corners[3], 0.50),
            _interpolate(corners[1], corners[2], 0.50),
            (0, 0, 255),
        ),
        (
            _interpolate(corners[0], corners[3], 0.66),
            _interpolate(corners[1], corners[2], 0.66),
            (255, 0, 255),
        ),
        (
            _interpolate(corners[0], corners[3], 0.34),
            _interpolate(corners[1], corners[2], 0.34),
            (255, 0, 255),
        ),
    ):
        cv2.line(image, _point_to_int(first), _point_to_int(second), color, thickness=2)
    return image


def _interpolate(first: np.ndarray, second: np.ndarray, ratio: float) -> np.ndarray:
    return cast(np.ndarray, first + (second - first) * ratio)


def _point_to_int(point: np.ndarray) -> tuple[int, int]:
    return (int(round(float(point[0]))), int(round(float(point[1]))))
