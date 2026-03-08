from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


class AlembicMigrationTests(unittest.TestCase):
    def test_upgrade_head_creates_expected_tables(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "migration.db"
            url = f"sqlite:///{db_path}"
            cfg = Config("/workspace/alembic.ini")
            cfg.set_main_option("script_location", "/workspace/alembic")
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
            }
            self.assertTrue(expected.issubset(tables))


if __name__ == "__main__":
    unittest.main()
