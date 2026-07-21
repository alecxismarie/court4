from dataclasses import dataclass

Point2D = tuple[float, float]


@dataclass(frozen=True)
class PickleballCourtDimensions:
    width_feet: float = 20.0
    length_feet: float = 44.0
    net_y_feet: float = 22.0
    non_volley_zone_depth_feet: float = 7.0

    @property
    def center_x_feet(self) -> float:
        return self.width_feet / 2.0

    @property
    def near_kitchen_y_feet(self) -> float:
        return self.net_y_feet - self.non_volley_zone_depth_feet

    @property
    def far_kitchen_y_feet(self) -> float:
        return self.net_y_feet + self.non_volley_zone_depth_feet


REGULATION_COURT = PickleballCourtDimensions()

COORDINATE_SYSTEM = {
    "unit": "feet",
    "origin": "near-left",
    "x_axis": "court-width",
    "y_axis": "court-length",
}

COURT_CORNERS: dict[str, Point2D] = {
    "near_left": (0.0, 0.0),
    "near_right": (REGULATION_COURT.width_feet, 0.0),
    "far_right": (REGULATION_COURT.width_feet, REGULATION_COURT.length_feet),
    "far_left": (0.0, REGULATION_COURT.length_feet),
}

ORDERED_CORNER_NAMES = ("near_left", "near_right", "far_right", "far_left")


def ordered_court_corner_points() -> tuple[Point2D, Point2D, Point2D, Point2D]:
    return (
        COURT_CORNERS["near_left"],
        COURT_CORNERS["near_right"],
        COURT_CORNERS["far_right"],
        COURT_CORNERS["far_left"],
    )
