from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from app.schemas.ball_tracking import (
    BallObservation,
    CalibrationEvidenceState,
    CourtProjectionMethod,
)
from app.schemas.calibration import (
    CalibrationVerificationRecord,
    CourtCalibrationReport,
    CourtProjectionAvailability,
    court_projection_availability,
)


@dataclass(frozen=True)
class BallProjectionResult:
    observations: tuple[BallObservation, ...]
    calibration_state: CalibrationEvidenceState


def project_ball_observations(
    observations: tuple[BallObservation, ...],
    *,
    calibration: CourtCalibrationReport | None,
    verification: CalibrationVerificationRecord | None,
    calibration_checksum_sha256: str | None,
) -> BallProjectionResult:
    """Attach approximate plane coordinates only for checksum-bound verified calibration."""
    availability = court_projection_availability(
        calibration,
        verification,
        calibration_checksum_sha256=calibration_checksum_sha256,
    )
    if availability == CourtProjectionAvailability.unavailable or calibration is None:
        return BallProjectionResult(
            observations=observations,
            calibration_state=(
                CalibrationEvidenceState.generated_unverified
                if calibration is not None
                else CalibrationEvidenceState.absent
            ),
        )

    matrix = np.asarray(calibration.image_to_court_matrix, dtype=np.float64)
    projected: list[BallObservation] = []
    for observation in observations:
        vector = matrix @ np.array(
            [observation.image_x, observation.image_y, 1.0],
            dtype=np.float64,
        )
        denominator = float(vector[2])
        if abs(denominator) <= 1e-12:
            projected.append(observation)
            continue
        court_x = float(vector[0] / denominator)
        court_y = float(vector[1] / denominator)
        if not math.isfinite(court_x) or not math.isfinite(court_y):
            projected.append(observation)
            continue
        projected.append(
            observation.model_copy(
                update={
                    "court_x": court_x,
                    "court_y": court_y,
                    "court_projection_method": (
                        CourtProjectionMethod.approximate_court_plane_projection
                    ),
                }
            )
        )
    return BallProjectionResult(
        observations=tuple(projected),
        calibration_state=CalibrationEvidenceState.verified,
    )
