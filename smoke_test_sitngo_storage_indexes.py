"""Storage-index regression for growing Sit&Go history/chat tables."""
from __future__ import annotations

from smoke_test_sitngo_phase1 import production_app as prod

EXPECTED = {
    "idx_sitngo_hands_event_created": ("sitngo_hands", ("event_id", "created_at", "hand_id")),
    "idx_sitngo_messages_event_created": ("sitngo_messages", ("event_id", "created_at", "id")),
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    db = prod.db
    with db.connect() as con:
        if getattr(db, "IS_POSTGRES", False):
            rows = con.execute(
                """SELECT indexname AS name,indexdef AS definition
                   FROM pg_indexes
                   WHERE schemaname=current_schema()
                     AND indexname IN (?,?)
                   ORDER BY indexname""",
                tuple(EXPECTED),
            ).fetchall()
        else:
            rows = con.execute(
                """SELECT name,sql AS definition
                   FROM sqlite_master
                   WHERE type='index' AND name IN (?,?)
                   ORDER BY name""",
                tuple(EXPECTED),
            ).fetchall()

    found = {str(row["name"]): str(row["definition"] or "") for row in rows}
    require(set(found) == set(EXPECTED), f"Sit&Go storage indexes missing: {set(EXPECTED)-set(found)}")
    for name, (_table, columns) in EXPECTED.items():
        definition = found[name].lower()
        position = -1
        for column in columns:
            next_position = definition.find(column.lower(), position + 1)
            require(next_position > position, f"{name} column order drifted: {definition}")
            position = next_position

    print("JJ_SITNGO_STORAGE_INDEXES_OK")


if __name__ == "__main__":
    main()
