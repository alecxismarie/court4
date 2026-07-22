import json
from pathlib import Path

from pydantic import BaseModel, ValidationError

from app.schemas.analytics import AnalyticsReport, TimelineReport
from app.schemas.match_iq import MatchIQReport
from app.services.match_iq.engine import generate_match_iq

MATCH_IQ_FILENAME = "match_iq.json"


class MatchIQPersistenceError(Exception):
    """Raised when persisted Match IQ cannot be read or written."""


def generate_and_write_match_iq(
    *,
    analytics: AnalyticsReport,
    timeline: TimelineReport | None,
    analytics_dir: Path,
) -> MatchIQReport:
    report = generate_match_iq(analytics=analytics, timeline=timeline)
    write_match_iq_report(report, analytics_dir / MATCH_IQ_FILENAME)
    return report


def load_match_iq_report(path: Path) -> MatchIQReport:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return MatchIQReport.model_validate(payload)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise MatchIQPersistenceError(f"Match IQ report could not be read: {path}") from exc


def write_match_iq_report(report: MatchIQReport, output_path: Path) -> None:
    _write_json(report, output_path)


def _write_json(model: BaseModel, output_path: Path) -> None:
    output_path.write_text(
        json.dumps(model.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
