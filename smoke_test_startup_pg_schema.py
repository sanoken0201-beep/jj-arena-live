"""Guard against PostgreSQL startup DDL deadlocks without a live database.

The existing-schema case must not issue any ALTER statements. A legacy schema
with missing columns or constraints must still be upgraded as before.
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from unittest.mock import patch

from materialized_v1244 import db


class Cursor:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


class FakePostgres:
    def __init__(self):
        self.columns = {
            "users": {"id", "name", "email", "password_hash", "arena_chips", "xp", "role", "created_at", "ranking_name"}
                     | {name for name, _ in db.PROFILE_COLUMNS},
            "sessions": {"token", "user_id", "expires_at", "created_at"},
            "schedules": {"id", "created_by", "created_at"},
            "announcements": {"id", "created_by", "created_at"},
            "threads": {"id", "author_id", "author_name", "created_at"},
            "replies": {"id", "author_id", "author_name", "created_at"},
        }
        self.constraints = {
            "arena_chips": {"column_default": "0", "is_nullable": "NO"},
            "xp": {"column_default": "'0'::integer", "is_nullable": "NO"},
        }
        self.statements = []

    @property
    def alters(self):
        return [sql for sql in self.statements if sql.strip().upper().startswith("ALTER TABLE")]

    def execute(self, sql, params=()):
        self.statements.append(sql)
        if "FROM information_schema.columns" in sql:
            if "column_default, is_nullable" in sql:
                return Cursor([self.constraints[params[0]]])
            return Cursor({"column_name": name} for name in sorted(self.columns.get(params[0], ())))
        match = re.match(r'ALTER TABLE (\w+) ADD COLUMN IF NOT EXISTS "?(\w+)"?', sql)
        if match:
            self.columns[match[1]].add(match[2])
        return Cursor()


@contextmanager
def use_fake_connection(con):
    yield con


def verify_normal_startup_is_read_only():
    con = FakePostgres()
    with patch.object(db, "IS_POSTGRES", True), patch.object(db, "connect", lambda: use_fake_connection(con)):
        db._migrate_legacy_beta(con)
        db.ensure_profile_columns()
    assert not con.alters, f"existing PostgreSQL schema still altered at boot: {con.alters}"


def verify_legacy_columns_are_still_added():
    con = FakePostgres()
    con.columns["sessions"].remove("expires_at")
    con.columns["users"].remove("profile_avatar")
    with patch.object(db, "IS_POSTGRES", True), patch.object(db, "connect", lambda: use_fake_connection(con)):
        db._migrate_legacy_beta(con)
        db.ensure_profile_columns()
    assert len(con.alters) == 2, f"unexpected legacy DDL: {con.alters}"
    assert "expires_at" in con.columns["sessions"]
    assert "profile_avatar" in con.columns["users"]


def verify_legacy_constraints_are_preserved():
    con = FakePostgres()
    con.constraints["arena_chips"] = {"column_default": None, "is_nullable": "YES"}
    con.constraints["xp"] = {"column_default": None, "is_nullable": "YES"}
    with patch.object(db, "IS_POSTGRES", True):
        db._migrate_legacy_beta(con)
    assert len(con.alters) == 4, f"expected default/NOT NULL repair: {con.alters}"
    assert all("ALTER TABLE users ALTER COLUMN" in sql for sql in con.alters)


def main():
    verify_normal_startup_is_read_only()
    verify_legacy_columns_are_still_added()
    verify_legacy_constraints_are_preserved()
    print("JJ_STARTUP_PG_SCHEMA_OK")


if __name__ == "__main__":
    main()
