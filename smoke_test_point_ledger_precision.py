from __future__ import annotations

import os
import sys
import uuid
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

import point_ledger_precision as precision

ROOT = Path(__file__).resolve().parent


class SQLiteLike:
    IS_POSTGRES = False


class PgConnection:
    def __init__(self, raw):
        self.raw = raw

    def execute(self, sql: str, params=()):
        return self.raw.execute(sql.replace("?", "%s"), params)


class PostgreSQLDB:
    IS_POSTGRES = True

    def __init__(self, url: str):
        self.url = url

    @contextmanager
    def connect(self):
        import psycopg
        from psycopg.rows import dict_row

        raw = psycopg.connect(self.url, row_factory=dict_row)
        try:
            yield PgConnection(raw)
            raw.commit()
        except Exception:
            raw.rollback()
            raise
        finally:
            raw.close()


def source_contract() -> None:
    assert precision.ensure_exact_point_ledger(SQLiteLike()) is False
    source = (ROOT / "point_ledger_precision.py").read_text(encoding="utf-8")
    assert "NUMERIC(12,2)" in source
    assert "migration refused" in source
    assert "ABS(amount::double precision" in source
    assert "ALTER COLUMN amount TYPE NUMERIC" in source

    materialized = (ROOT / "app_materialized.py").read_text(encoding="utf-8")
    legacy = (ROOT / "app_legacy.py").read_text(encoding="utf-8")
    for app_source in (materialized, legacy):
        assert "import point_ledger_precision" in app_source
        assert "point_ledger_precision.ensure_exact_point_ledger(db)" in app_source


def postgres_contract() -> None:
    url = os.environ.get("DATABASE_URL", "")
    parsed = urlsplit(url)
    assert parsed.hostname in {"127.0.0.1", "localhost"} and parsed.path == "/jj_arena_ci", (
        "Only the local disposable jj_arena_ci PostgreSQL database is allowed"
    )
    db = PostgreSQLDB(url)
    suffix = uuid.uuid4().hex[:12]
    good = f"point_ledger_precision_{suffix}"
    bad = f"point_ledger_precision_bad_{suffix}"

    try:
        with db.connect() as con:
            con.execute(f"CREATE TABLE {good}(id TEXT PRIMARY KEY, amount REAL NOT NULL)")
            for key, value in (("a", 0.1), ("b", 1.23), ("c", -5.5), ("d", 10.0)):
                con.execute(f"INSERT INTO {good}(id,amount) VALUES (?,?)", (key, value))

        assert precision.ensure_exact_point_ledger(db, good) is True
        contract = precision._column_contract(db, good)
        assert contract is not None
        assert contract["data_type"] == "numeric"
        assert int(contract["numeric_precision"]) == 12
        assert int(contract["numeric_scale"]) == 2
        assert precision.ensure_exact_point_ledger(db, good) is False

        with db.connect() as con:
            rows = con.execute(f"SELECT id,amount FROM {good} ORDER BY id").fetchall()
            total = con.execute(f"SELECT SUM(amount) total FROM {good}").fetchone()["total"]
        values = {str(row["id"]): row["amount"] for row in rows}
        assert values == {
            "a": Decimal("0.10"),
            "b": Decimal("1.23"),
            "c": Decimal("-5.50"),
            "d": Decimal("10.00"),
        }
        assert total == Decimal("5.83")

        with db.connect() as con:
            con.execute(f"CREATE TABLE {bad}(id TEXT PRIMARY KEY, amount REAL NOT NULL)")
            con.execute(f"INSERT INTO {bad}(id,amount) VALUES (?,?)", ("bad", 1.234))
        try:
            precision.ensure_exact_point_ledger(db, bad)
        except RuntimeError as exc:
            assert "migration refused" in str(exc)
        else:
            raise AssertionError("three-decimal legacy amount was silently migrated")

        bad_contract = precision._column_contract(db, bad)
        assert bad_contract is not None and bad_contract["data_type"] == "real"
        with db.connect() as con:
            value = float(con.execute(f"SELECT amount FROM {bad} WHERE id='bad'").fetchone()["amount"])
        assert abs(value - 1.234) < 0.00001
    finally:
        with db.connect() as con:
            con.execute(f"DROP TABLE IF EXISTS {good}")
            con.execute(f"DROP TABLE IF EXISTS {bad}")


def main() -> None:
    source_contract()
    if "--postgres" in sys.argv:
        postgres_contract()
        print("JJ_POINT_LEDGER_PRECISION_POSTGRES_OK")
    else:
        print("JJ_POINT_LEDGER_PRECISION_SOURCE_OK")


if __name__ == "__main__":
    main()
