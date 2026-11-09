#!/usr/bin/env python3
"""
Explicit, idempotent SQLite migration script for ENVshare User authentication columns.

Adds:
- token_version (INTEGER NOT NULL DEFAULT 1)
- reset_token_hash (VARCHAR NULL)
- reset_token_expires_at (DATETIME NULL)

Usage:
    python backend/migrate_auth.py [path/to/envshare.db]
"""
import os
import sqlite3
import sys
from pathlib import Path

def migrate_database(db_path: str = None) -> bool:
    if not db_path:
        base_dir = Path(__file__).resolve().parent
        db_path = str(base_dir / "envshare.db")

    if not os.path.exists(db_path):
        print(f"Error: Database file does not exist at {db_path}", file=sys.stderr)
        return False

    print(f"Running auth migration on database: {db_path}")
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()

        # Check existing table counts before migration
        pre_counts = {}
        for table in ["users", "projects", "project_members", "environments",
                      "project_invitations", "variables", "history_logs", "environment_snapshots"]:
            try:
                cursor.execute(f"SELECT count(*) FROM {table}")
                pre_counts[table] = cursor.fetchone()[0]
            except sqlite3.OperationalError:
                pass

        # Inspect current users table columns
        cursor.execute("PRAGMA table_info(users)")
        columns_info = cursor.fetchall()
        existing_cols = {col[1] for col in columns_info}
        print(f"Existing columns in 'users': {sorted(list(existing_cols))}")

        altered = False

        if "token_version" not in existing_cols:
            print("Adding column 'token_version' to 'users' table...")
            cursor.execute("ALTER TABLE users ADD COLUMN token_version INTEGER NOT NULL DEFAULT 1")
            cursor.execute("UPDATE users SET token_version = 1 WHERE token_version IS NULL")
            altered = True
        else:
            print("Column 'token_version' already exists.")

        if "reset_token_hash" not in existing_cols:
            print("Adding column 'reset_token_hash' to 'users' table...")
            cursor.execute("ALTER TABLE users ADD COLUMN reset_token_hash VARCHAR")
            altered = True
        else:
            print("Column 'reset_token_hash' already exists.")

        if "reset_token_expires_at" not in existing_cols:
            print("Adding column 'reset_token_expires_at' to 'users' table...")
            cursor.execute("ALTER TABLE users ADD COLUMN reset_token_expires_at DATETIME")
            altered = True
        else:
            print("Column 'reset_token_expires_at' already exists.")

        conn.commit()

        # Verify post-migration table counts
        post_counts = {}
        for table in pre_counts:
            cursor.execute(f"SELECT count(*) FROM {table}")
            post_counts[table] = cursor.fetchone()[0]
            if post_counts[table] != pre_counts[table]:
                raise RuntimeError(
                    f"Count mismatch in table '{table}': {pre_counts[table]} before, {post_counts[table]} after!"
                )

        print("Migration completed successfully. Record counts verified:")
        for t, count in post_counts.items():
            print(f"  - {t}: {count}")

        return True
    except Exception as exc:
        conn.rollback()
        print(f"Migration error: {exc}", file=sys.stderr)
        return False
    finally:
        conn.close()

if __name__ == "__main__":
    target_db = sys.argv[1] if len(sys.argv) > 1 else None
    success = migrate_database(target_db)
    sys.exit(0 if success else 1)

