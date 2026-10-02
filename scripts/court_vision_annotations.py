"""Offline-only court-vision annotation contract; never imported by production."""

from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

Number = Annotated[float, Field(allow_inf_nan=False)]
Nonnegative = Annotated[Number, Field(ge=0)]
Identifier = Annotated[str, Field(min_length=1, pattern=r"^[A-Za-z0-9_.-]+$")]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Point = tuple[Nonnegative, Nonnegative]

# Order and reference-edge semantics are fixed by annotation_convention below.
KEYPOINTS = {
    "near_left": (0.0, 0.0),
    "near_right": (20.0, 0.0),
    "far_right": (20.0, 44.0),
    "far_left": (0.0, 44.0),
    "near_nvz_left": (0.0, 15.0),
    "near_nvz_right": (20.0, 15.0),
    "far_nvz_left": (0.0, 29.0),
    "far_nvz_right": (20.0, 29.0),
    "near_baseline_center": (10.0, 0.0),
    "near_nvz_center": (10.0, 15.0),
    "far_nvz_center": (10.0, 29.0),
    "far_baseline_center": (10.0, 44.0),
}
LINES = {
    "near_baseline": ((0.0, 0.0), (20.0, 0.0)),
    "far_baseline": ((0.0, 44.0), (20.0, 44.0)),
    "left_sideline": ((0.0, 0.0), (0.0, 44.0)),
    "right_sideline": ((20.0, 0.0), (20.0, 44.0)),
    "near_nvz": ((0.0, 15.0), (20.0, 15.0)),
    "far_nvz": ((0.0, 29.0), (20.0, 29.0)),
    "near_center_service": ((10.0, 0.0), (10.0, 15.0)),
    "far_center_service": ((10.0, 29.0), (10.0, 44.0)),
}
CORNERS = tuple(KEYPOINTS)[:4]
REQUIRED_LINES = tuple(LINES)[:6]


def keypoint_schema(schema: dict[str, Any]) -> None:
    schema.update(
        properties={name: schema["additionalProperties"] for name in KEYPOINTS},
        required=list(KEYPOINTS),
        additionalProperties=False,
    )


def line_schema(schema: dict[str, Any]) -> None:
    schema.update(
        properties={name: schema["additionalProperties"] for name in LINES},
        required=list(LINES),
        additionalProperties=False,
    )


class AnnotationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Keypoint(AnnotationModel):
    visibility: Literal["visible", "occluded_localizable", "outside_frame", "unknown"]
    xy: Point | None = None
    uncertainty_px: Nonnegative | None = None

    @model_validator(mode="after")
    def check_location(self) -> Self:
        localized = self.visibility in {"visible", "occluded_localizable"}
        if localized != (self.xy is not None and self.uncertainty_px is not None):
            raise ValueError("Localized points require xy and uncertainty_px.")
        if not localized and (self.xy is not None or self.uncertainty_px is not None):
            raise ValueError("Unknown/offscreen points must not contain guessed coordinates.")
        return self


class LineRun(AnnotationModel):
    """One uninterrupted visible reference-edge/center polyline, in original pixels."""

    points: Annotated[list[Point], Field(min_length=2)]

    @model_validator(mode="after")
    def check_length(self) -> Self:
        if any(a == b for a, b in zip(self.points, self.points[1:], strict=False)):
            raise ValueError("Consecutive line points must be distinct.")
        return self


class LineAnnotation(AnnotationModel):
    reference: Literal["outside_perimeter", "away_from_net", "stripe_center"]
    visible_runs: list[LineRun]
    uncertainty_px: Nonnegative
    paint_width_px: Annotated[Number, Field(gt=0)] | None = None
    unobserved_reason: Literal["none", "occluded", "outside_frame", "unknown", "mixed"]

    @model_validator(mode="after")
    def check_evidence(self) -> Self:
        if not self.visible_runs and self.unobserved_reason == "none":
            raise ValueError("An unobserved line requires a missing-evidence reason.")
        return self


class FrameAnnotation(AnnotationModel):
    frame_id: Identifier
    image_path: str = Field(min_length=1)
    image_sha256: Digest
    source_video_sha256: Digest | None = None
    source_reference: str = Field(min_length=1)
    usage_provenance: str = Field(min_length=1)
    recording_id: Identifier
    venue_id: Identifier
    court_id: Identifier
    camera_setup_id: Identifier
    shot_id: Identifier
    split: Literal["development", "train", "validation", "test"]
    data_kind: Literal["real", "synthetic"]
    frame_number: Annotated[int, Field(gt=0)]
    timestamp_seconds: Nonnegative
    width: Annotated[int, Field(gt=0)]
    height: Annotated[int, Field(gt=0)]
    coordinate_space: Literal["original_decoded_pixels"]
    orientation: Literal["camera_relative_near_left", "unresolved"]
    camera_motion: Literal["stationary", "moving", "unknown"]
    suitability: Literal["full_geometry_supported", "partial_or_ambiguous", "no_target_court"]
    reasons: list[str]
    tags: list[str]
    annotator: str = Field(min_length=1)
    reviewer: str | None = None
    review_status: Literal["draft", "reviewed"]
    keypoints: dict[str, Keypoint] = Field(json_schema_extra=keypoint_schema)
    lines: dict[str, LineAnnotation] = Field(json_schema_extra=line_schema)

    @model_validator(mode="after")
    def check_frame(self) -> Self:
        if set(self.keypoints) != set(KEYPOINTS):
            raise ValueError("Exactly the 12 named keypoints are required, including unknowns.")
        if set(self.lines) != set(LINES):
            raise ValueError("Exactly the eight named physical lines are required.")
        if self.review_status == "reviewed" and (
            not self.reviewer or self.reviewer == self.annotator
        ):
            raise ValueError("Reviewed labels require a distinct reviewer.")
        for name, line in self.lines.items():
            reference = (
                "stripe_center"
                if "center_service" in name
                else "away_from_net"
                if "nvz" in name
                else "outside_perimeter"
            )
            if line.reference != reference:
                raise ValueError(f"Wrong reference edge for {name}.")
        points = [p.xy for p in self.keypoints.values() if p.xy is not None]
        points.extend(
            p for line in self.lines.values() for run in line.visible_runs for p in run.points
        )
        if any(x >= self.width or y >= self.height for x, y in points):
            raise ValueError("Annotations must lie within the decoded image.")
        if self.suitability == "no_target_court" and (
            any(p.visibility != "unknown" for p in self.keypoints.values())
            or any(line.visible_runs for line in self.lines.values())
        ):
            raise ValueError("No-target frames cannot contain target-court geometry.")
        return self


class BenchmarkManifest(AnnotationModel):
    schema_version: Literal["court-vision-annotations-v1"]
    template_version: Literal["pickleball-court-v1"]
    annotation_convention: Literal["outside-perimeter-nvz-away-service-center-v1"]
    dataset_id: Identifier
    frames: list[FrameAnnotation]

    @model_validator(mode="after")
    def unique_ids(self) -> Self:
        ids = [frame.frame_id for frame in self.frames]
        if len(ids) != len(set(ids)):
            raise ValueError("Frame IDs must be unique.")
        return self
