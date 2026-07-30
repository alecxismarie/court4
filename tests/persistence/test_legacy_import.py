from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from app.persistence.legacy import import_legacy_source, inventory_legacy_source
from app.persistence.runtime import get_persistence


def test_legacy_inventory_import_and_repeat_are_safe(tmp_path: Path) -> None:
    runtime = get_persistence()
    source = tmp_path / "legacy"
    analysis_dir = source / "legacy-preserved"
    analytics_dir = analysis_dir / "analytics"
    analytics_dir.mkdir(parents=True)
    now = datetime.now(tz=UTC).isoformat()
    job_path = analysis_dir / "job.json"
    job_path.write_text(
        json.dumps(
            {
                "analysis_id": "legacy-preserved",
                "status": "completed",
                "current_stage": "analyzed",
                "created_at": now,
                "updated_at": now,
                "analytics_completed": True,
            }
        ),
        encoding="utf-8",
    )
    report_path = analytics_dir / "analytics.json"
    report_path.write_text('{"schema":"legacy"}', encoding="utf-8")
    unrelated = source / "tool-output"
    unrelated.mkdir()

    inventory = inventory_legacy_source(source)
    assert inventory.summary()["classifications"] == {"valuable": 1}
    assert inventory.non_analysis_directories == ("tool-output",)

    dry_run = import_legacy_source(
        source=source,
        service=runtime.service,
        owner_user_id=runtime.owner_user_id,
        dry_run=True,
    )
    assert dry_run["imported"] == []
    assert runtime.service.list_analysis_ids(owner_user_id=runtime.owner_user_id) == []

    first = import_legacy_source(
        source=source,
        service=runtime.service,
        owner_user_id=runtime.owner_user_id,
        dry_run=False,
    )
    second = import_legacy_source(
        source=source,
        service=runtime.service,
        owner_user_id=runtime.owner_user_id,
        dry_run=False,
    )
    assert first["imported"] == ["legacy-preserved"]
    assert second["already_present"] == ["legacy-preserved"]
    assert job_path.is_file()
    assert report_path.read_text(encoding="utf-8") == '{"schema":"legacy"}'
    assert runtime.service.list_analysis_ids(
        owner_user_id=runtime.owner_user_id
    ) == ["legacy-preserved"]
