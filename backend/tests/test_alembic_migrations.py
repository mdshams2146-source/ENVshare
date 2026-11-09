import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

# Ensure backend root is on sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from alembic.config import Config
from alembic import command


class TestAlembicMigrations(unittest.TestCase):
    def setUp(self):
        self.alembic_ini_path = str(backend_dir / "alembic.ini")

    def test_fresh_database_upgrade_head(self):
        """Verify that running 'alembic upgrade head' on a fresh database creates all tables and columns."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "fresh_test.db")
            db_url = f"sqlite:///{db_path}"

            cfg = Config(self.alembic_ini_path)
            cfg.set_main_option("sqlalchemy.url", db_url)

            command.upgrade(cfg, "head")

            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            tables = {r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            expected_tables = {
                "users",
                "projects",
                "project_members",
                "environments",
                "variables",
                "history_logs",
                "project_invitations",
                "environment_snapshots",
                "alembic_version"
            }
            self.assertTrue(expected_tables.issubset(tables))

            # Verify all required columns on users
            user_cols = {c[1] for c in cur.execute("PRAGMA table_info(users)").fetchall()}
            self.assertIn("token_version", user_cols)
            self.assertIn("reset_token_hash", user_cols)
            self.assertIn("reset_token_expires_at", user_cols)

            # Verify version table head
            version = cur.execute("SELECT version_num FROM alembic_version").fetchone()[0]
            self.assertEqual(version, "0002_add_auth_columns")
            conn.close()

    def test_existing_database_upgrade_preserves_data(self):
        """Verify that running 'alembic upgrade head' on an existing installation preserves tables and records."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "existing_sim.db")
            real_db = backend_dir / "envshare.db"

            # Create realistic test database with existing records
            real_conn = sqlite3.connect(str(real_db))
            test_conn = sqlite3.connect(db_path)
            real_conn.backup(test_conn)
            real_conn.close()

            # Record baseline counts
            cur = test_conn.cursor()
            user_count_before = cur.execute("SELECT count(*) FROM users").fetchone()[0]
            var_count_before = cur.execute("SELECT count(*) FROM variables").fetchone()[0]
            test_conn.close()

            cfg = Config(self.alembic_ini_path)
            cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")

            # Upgrade head should safely run without table-recreation errors
            command.upgrade(cfg, "head")

            check_conn = sqlite3.connect(db_path)
            check_cur = check_conn.cursor()
            user_count_after = check_cur.execute("SELECT count(*) FROM users").fetchone()[0]
            var_count_after = check_cur.execute("SELECT count(*) FROM variables").fetchone()[0]
            version = check_cur.execute("SELECT version_num FROM alembic_version").fetchone()[0]

            self.assertEqual(user_count_before, user_count_after)
            self.assertEqual(var_count_before, var_count_after)
            self.assertEqual(version, "0002_add_auth_columns")
            check_conn.close()


if __name__ == "__main__":
    unittest.main()

