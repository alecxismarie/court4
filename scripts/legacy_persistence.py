from __future__ import annotations

import argparse
import json
from pathlib import Path
from uuid import UUID

from app.config import get_settings
from app.persistence.bootstrap import BootstrapIdentity
from app.persistence.database import create_database_engine, create_session_factory
from app.persistence.legacy import import_legacy_source, inventory_legacy_source
from app.persistence.service import PersistenceService


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inventory or explicitly import Court4 job.json legacy records."
    )
    parser.add_argument("action", choices=("inventory", "dry-run", "import"))
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--owner-id", type=UUID)
    parser.add_argument("--owner-identity")
    parser.add_argument("--environment", required=True)
    args = parser.parse_args()
    settings = get_settings()
    if args.environment != settings.environment:
        parser.error("--environment must exactly match PICKLEBALL_AI_ENVIRONMENT")

    if args.action == "inventory":
        print(json.dumps(inventory_legacy_source(args.source).summary(), indent=2))
        return 0
    if args.owner_id is None or not args.owner_identity:
        parser.error("dry-run and import require explicit --owner-id and --owner-identity")
    if args.action == "import" and not settings.legacy_import_enabled:
        parser.error("import requires PICKLEBALL_AI_LEGACY_IMPORT_ENABLED=true")

    engine = create_database_engine(settings)
    service = PersistenceService(create_session_factory(engine))
    if args.action == "import":
        service.ensure_bootstrap_user(BootstrapIdentity(args.owner_id, args.owner_identity))
    result = import_legacy_source(
        source=args.source,
        service=service,
        owner_user_id=args.owner_id,
        dry_run=args.action == "dry-run",
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
