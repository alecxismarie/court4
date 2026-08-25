from dataclasses import dataclass

Point2D = tuple[float, float]
LineSegment = tuple[Point2D, Point2D]


@dataclass(frozen=True)
class PadelCourtDefinition:
    """Regulation doubles court geometry without wall-event interpretation."""

    width_metres: float = 10.0
    length_metres: float = 20.0
    net_y_metres: float = 10.0
    service_line_distance_from_net_metres: float = 6.95
    boundary_semantics: str = "enclosure_playable_wall_interactions_unmodelled"
    version: str = "padel-court-v1"

    @property
    def center_x_metres(self) -> float:
        return self.width_metres / 2.0

    @property
    def near_service_line_y_metres(self) -> float:
        return self.net_y_metres - self.service_line_distance_from_net_metres

    @property
    def far_service_line_y_metres(self) -> float:
        return self.net_y_metres + self.service_line_distance_from_net_metres

    @property
    def boundaries(self) -> tuple[LineSegment, ...]:
        return (
            ((0.0, 0.0), (self.width_metres, 0.0)),
            ((self.width_metres, 0.0), (self.width_metres, self.length_metres)),
            ((self.width_metres, self.length_metres), (0.0, self.length_metres)),
            ((0.0, self.length_metres), (0.0, 0.0)),
        )

    @property
    def net(self) -> LineSegment:
        return ((0.0, self.net_y_metres), (self.width_metres, self.net_y_metres))

    @property
    def service_lines(self) -> tuple[LineSegment, LineSegment]:
        return (
            (
                (0.0, self.near_service_line_y_metres),
                (self.width_metres, self.near_service_line_y_metres),
            ),
            (
                (0.0, self.far_service_line_y_metres),
                (self.width_metres, self.far_service_line_y_metres),
            ),
        )

    @property
    def centre_service_lines(self) -> tuple[LineSegment, LineSegment]:
        return (
            (
                (self.center_x_metres, 0.0),
                (self.center_x_metres, self.near_service_line_y_metres),
            ),
            (
                (self.center_x_metres, self.far_service_line_y_metres),
                (self.center_x_metres, self.length_metres),
            ),
        )


PADEL_COURT = PadelCourtDefinition()
