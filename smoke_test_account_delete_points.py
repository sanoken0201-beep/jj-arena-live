from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

WORK = Path(tempfile.mkdtemp(prefix="jj-account-delete-points-"))
if not os.environ.get("DATABASE_URL"):
    os.environ["JJ_DB_PATH"] = str(WORK / "delete-points.db")
os.environ.pop("JJ_ADMIN_PIN", None)
os.environ.pop("JJ_ADMIN_LOGIN_PASSWORD", None)
os.environ.pop("JJ_ADMIN_LOGIN_EMAIL", None)


def route(app, path: str, method: str):
    method = method.upper()
    for r in app.router.routes:
        if getattr(r, "path", None) == path and method in (getattr(r, "methods", None) or set()):
            return r
    raise AssertionError((path, method))


def ranking_for(rows, name: str):
    return next((row for row in rows if row["name"] == name), None)


def main() -> None:
    from app import app
    import db
    import server
    from admin_console import _rankings

    name = "削除ポイント失効テスト"
    with db.connect() as con:
        admin = con.execute("SELECT id,name,role FROM users WHERE role='admin' ORDER BY id LIMIT 1").fetchone()
        if not admin:
            admin_id = db.insert_returning_id(
                con,
                "INSERT INTO users(name,email,password_hash,role,arena_chips,xp,approved,disabled,ranking_name,created_at,club_verified,admin_note) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                ("テスト管理者", "delete-points-admin@jj.invalid", db.hash_password("test"), "admin", 0, 0, 1, 0, "テスト管理者", "2026-09-01T00:00:00+00:00", 1, ""),
            )
            admin = con.execute("SELECT id,name,role FROM users WHERE id=?", (admin_id,)).fetchone()
        uid = db.insert_returning_id(
            con,
            "INSERT INTO users(name,email,password_hash,role,arena_chips,xp,approved,disabled,ranking_name,created_at,club_verified,admin_note) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (name, "delete-points-old@jj.invalid", db.hash_password("member"), "member", 0, 0, 1, 0, name, "2026-09-01T00:00:00+00:00", 1, ""),
        )
        con.execute(
            "INSERT INTO entries(id,date,name,remaining,reentries,initial,points,game,game_type,source,created_by,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            ("delete-points-entry-old", "2026-09-05", name, 0, 0, 1, 40, "delete points", "ring", "regression", int(admin["id"]), "2026-09-05T12:00:00+00:00"),
        )
        con.execute(
            "INSERT INTO online_hands(hand_id,table_id,hand_no,gross_pot_bb,rake_bb,played_at,month,voided) VALUES (?,?,?,?,?,?,?,0)",
            ("delete-points-hand-old", "jj-table-a", 1, 10, 0, "2026-09-06T12:00:00+00:00", "2026-09"),
        )
        con.execute(
            "INSERT INTO online_hand_results(id,hand_id,table_id,user_id,ranking_name,result_bb,points,month,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            ("delete-points-result-old", "delete-points-hand-old", "jj-table-a", uid, name, 5, 15, "2026-09", "2026-09-06T12:00:00+00:00"),
        )
        con.execute(
            "INSERT INTO point_ledger(id,user_id,amount,kind,reason,effective_at,created_by,created_at,reversal_of) VALUES (?,?,?,?,?,?,?,?,NULL)",
            ("delete-points-ledger-old", uid, 25, "credit", "delete points regression", "2026-09-07T12:00:00+00:00", int(admin["id"]), "2026-09-07T12:00:00+00:00"),
        )

    before = ranking_for(_rankings(db, server, season="fall"), name)
    assert before is not None
    assert before["club_points"] == 40.0
    assert before["online_points"] == 15.0
    assert before["admin_points"] == 25.0
    assert before["points"] == 80.0

    admin_user = {"id": int(admin["id"]), "name": str(admin["name"]), "role": "admin"}
    deleted = route(app, "/api/admin/console/users/{uid}", "DELETE").endpoint(uid=uid, user=admin_user)
    assert deleted["ok"] is True

    with db.connect() as con:
        con.execute("UPDATE users SET deleted_at=? WHERE id=?", ("2026-09-10T00:00:00+00:00", uid))

    after = ranking_for(_rankings(db, server, season="fall"), name)
    assert after is None, after

    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) n FROM entries WHERE id='delete-points-entry-old'").fetchone()["n"] == 1
        assert con.execute("SELECT COUNT(*) n FROM online_hand_results WHERE id='delete-points-result-old'").fetchone()["n"] == 1
        assert con.execute("SELECT COUNT(*) n FROM point_ledger WHERE id='delete-points-ledger-old'").fetchone()["n"] == 1

        new_uid = db.insert_returning_id(
            con,
            "INSERT INTO users(name,email,password_hash,role,arena_chips,xp,approved,disabled,ranking_name,created_at,club_verified,admin_note) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (name, "delete-points-new@jj.invalid", db.hash_password("member"), "member", 0, 0, 1, 0, name, "2026-09-11T00:00:00+00:00", 1, ""),
        )
        con.execute(
            "INSERT INTO entries(id,date,name,remaining,reentries,initial,points,game,game_type,source,created_by,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            ("delete-points-entry-stale", "2026-09-10", name, 0, 0, 1, 99, "delete points", "ring", "regression", int(admin["id"]), "2026-09-10T12:00:00+00:00"),
        )
        con.execute(
            "INSERT INTO entries(id,date,name,remaining,reentries,initial,points,game,game_type,source,created_by,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            ("delete-points-entry-new", "2026-09-12", name, 0, 0, 1, 8, "delete points", "ring", "regression", int(admin["id"]), "2026-09-12T12:00:00+00:00"),
        )
        con.execute(
            "INSERT INTO online_hands(hand_id,table_id,hand_no,gross_pot_bb,rake_bb,played_at,month,voided) VALUES (?,?,?,?,?,?,?,0)",
            ("delete-points-hand-new", "jj-table-a", 2, 10, 0, "2026-09-12T12:00:00+00:00", "2026-09"),
        )
        con.execute(
            "INSERT INTO online_hand_results(id,hand_id,table_id,user_id,ranking_name,result_bb,points,month,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            ("delete-points-result-new", "delete-points-hand-new", "jj-table-a", new_uid, name, 2, 6, "2026-09", "2026-09-12T12:00:00+00:00"),
        )
        con.execute(
            "INSERT INTO point_ledger(id,user_id,amount,kind,reason,effective_at,created_by,created_at,reversal_of) VALUES (?,?,?,?,?,?,?,?,NULL)",
            ("delete-points-ledger-new", new_uid, 4, "credit", "new generation", "2026-09-12T12:00:00+00:00", int(admin["id"]), "2026-09-12T12:00:00+00:00"),
        )

    fresh = ranking_for(_rankings(db, server, season="fall"), name)
    assert fresh is not None
    print("ACCOUNT_DELETE_POINT_EXPIRY_FRESH", fresh, flush=True)
    assert fresh["club_points"] == 8.0
    assert fresh["online_points"] == 6.0
    assert fresh["admin_points"] == 4.0
    assert fresh["points"] == 18.0
    print("ACCOUNT_DELETE_POINT_EXPIRY_OK", flush=True)


if __name__ == "__main__":
    try:
        main()
    finally:
        shutil.rmtree(WORK, ignore_errors=True)
