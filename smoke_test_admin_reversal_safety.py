from __future__ import annotations

import sqlite3
import tempfile
from contextlib import contextmanager
from pathlib import Path

from admin_ledger_stabilization import _claim_reversal, _ensure_reversal_claims


class TestDb:
    IS_POSTGRES = False

    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="jj-reversal-safety-") as directory:
        db = TestDb(Path(directory) / "ledger.db")
        with db.connect() as con:
            con.execute(
                """
                CREATE TABLE point_ledger(
                    id TEXT PRIMARY KEY,
                    reversal_of TEXT REFERENCES point_ledger(id),
                    created_at TEXT NOT NULL
                )
                """
            )
            con.execute("INSERT INTO point_ledger(id,reversal_of,created_at) VALUES ('orig',NULL,'2026-09-17T00:00:00Z')")
            # Historical reversal is backfilled without rewriting ledger data.
            con.execute("INSERT INTO point_ledger(id,reversal_of,created_at) VALUES ('old-rv','orig','2026-09-17T00:01:00Z')")

        _ensure_reversal_claims(db)
        with db.connect() as con:
            claim = con.execute(
                "SELECT reversal_id FROM point_ledger_reversal_claims WHERE reversal_of='orig'"
            ).fetchone()
            assert claim and claim["reversal_id"] == "old-rv"
            assert not _claim_reversal(con, "orig", "duplicate-rv", "2026-09-17T00:02:00Z")
            assert con.execute(
                "SELECT COUNT(*) n FROM point_ledger_reversal_claims WHERE reversal_of='orig'"
            ).fetchone()["n"] == 1

        # A new original can be claimed exactly once. The claim is deliberately
        # inserted before the reversal ledger row so concurrent workers cannot
        # both pass a read-before-write check.
        with db.connect() as con:
            con.execute("INSERT INTO point_ledger(id,reversal_of,created_at) VALUES ('orig-2',NULL,'2026-09-17T01:00:00Z')")
            assert _claim_reversal(con, "orig-2", "rv-2", "2026-09-17T01:01:00Z")
            con.execute("INSERT INTO point_ledger(id,reversal_of,created_at) VALUES ('rv-2','orig-2','2026-09-17T01:01:00Z')")
            assert not _claim_reversal(con, "orig-2", "rv-3", "2026-09-17T01:02:00Z")

        print("JJ_ADMIN_REVERSAL_SAFETY_OK")


if __name__ == "__main__":
    main()
