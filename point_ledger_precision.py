from __future__ import annotations

"""Exact PostgreSQL storage contract for JJ Arena point-ledger amounts.

The historical root admin console created ``point_ledger.amount`` as PostgreSQL
``REAL``. All product writers already constrain meaningful values to at most two
decimal places, but binary floating-point aggregation is unnecessary for points.
This compatibility migration changes only PostgreSQL ledger storage to
``NUMERIC(12,2)``. SQLite keeps its existing affinity for local/test parity.

Migration is deliberately fail-closed: if an existing row contains a meaningful
third decimal place or cannot fit NUMERIC(12,2), startup raises instead of
silently rounding or truncating production point history.
"""

import re
from typing import Any

_PRECISION = 12
_SCALE = 2
_MAX_ABS_EXCLUSIVE = 10 ** (_PRECISION - _SCALE)
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validated_table(table: str) -> str:
    if not _IDENTIFIER.fullmatch(str(table or "")):
        raise ValueError("invalid ledger table identifier")
    return table


def _column_contract(db, table: str) -> dict[str, Any] | None:
    with db.connect() as con:
        row = con.execute(
            """SELECT data_type,numeric_precision,numeric_scale
               FROM information_schema.columns
               WHERE table_schema='public' AND table_name=? AND column_name='amount'""",
            (table,),
        ).fetchone()
    return dict(row) if row else None


def ensure_exact_point_ledger(db, table: str = "point_ledger") -> bool:
    """Ensure PostgreSQL ledger amounts use NUMERIC(12,2).

    Returns True when a migration was applied and False for SQLite, an absent
    table/column, or an already-correct PostgreSQL contract.
    """
    if not bool(getattr(db, "IS_POSTGRES", False)):
        return False
    table = _validated_table(table)
    current = _column_contract(db, table)
    if not current:
        return False
    if (
        str(current.get("data_type") or "").lower() == "numeric"
        and int(current.get("numeric_precision") or 0) == _PRECISION
        and int(current.get("numeric_scale") or -1) == _SCALE
    ):
        return False

    with db.connect() as con:
        incompatible = con.execute(
            f"""SELECT COUNT(*) n FROM {table}
                WHERE amount IS NOT NULL AND (
                    ABS(amount::double precision - ROUND(amount::numeric, {_SCALE})::double precision) > 0.000001
                    OR ABS(amount::numeric) >= ?
                )""",
            (_MAX_ABS_EXCLUSIVE,),
        ).fetchone()
        count = int(incompatible["n"] or 0)
        if count:
            raise RuntimeError(
                f"point ledger precision migration refused: {count} row(s) require rounding or exceed NUMERIC({_PRECISION},{_SCALE})"
            )
        con.execute(
            f"""ALTER TABLE {table}
                ALTER COLUMN amount TYPE NUMERIC({_PRECISION},{_SCALE})
                USING ROUND(amount::numeric, {_SCALE})"""
        )

    migrated = _column_contract(db, table)
    if not migrated or not (
        str(migrated.get("data_type") or "").lower() == "numeric"
        and int(migrated.get("numeric_precision") or 0) == _PRECISION
        and int(migrated.get("numeric_scale") or -1) == _SCALE
    ):
        raise RuntimeError("point ledger precision migration did not establish NUMERIC(12,2)")
    return True


__all__ = ["ensure_exact_point_ledger"]
