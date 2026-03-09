from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


class AlembicMigrationTests(unittest.TestCase):
    def test_upgrade_head_creates_expected_tables(self) -> None:
        root = _project_root()
        alembic_ini = root / "alembic.ini"
        script_location = root / "alembic"
        if not alembic_ini.exists() or not script_location.is_dir():
            self.skipTest("alembic.ini or alembic/ not found")
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "migration.db"
            url = f"sqlite:///{db_path}"
            cfg = Config(str(alembic_ini))
            cfg.set_main_option("script_location", str(script_location))
            cfg.set_main_option("sqlalchemy.url", url)
            command.upgrade(cfg, "head")

            engine = create_engine(url)
            inspector = inspect(engine)
            tables = set(inspector.get_table_names())
            expected = {
                "principals",
                "tokens",
                "packages",
                "installs",
                "billing_events",
                "invoice_lines",
                "queue_messages",
                "audit_events",
                "payment_records",
                "package_reviews",
                "agent_projects",
                "project_maintainers",
                "project_branches",
                "project_contributions",
                "project_releases",
            }
            self.assertTrue(expected.issubset(tables), f"Missing tables: {expected - tables}")


if __name__ == "__main__":
    unittest.main()
