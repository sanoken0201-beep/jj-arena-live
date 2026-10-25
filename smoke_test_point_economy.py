"""Point-history attribution, inflation totals and authorization regression."""
import atexit
import os
import sys
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

if "--postgres" in sys.argv:
    # Use an isolated disposable database; never write fixtures to production
    # or another integration job's shared jj_arena_ci database.
    import psycopg
    from psycopg import sql

    original_url = os.environ.get("DATABASE_URL", "")
    parsed_url = urlsplit(original_url)
    assert (parsed_url.scheme in {"postgres", "postgresql"}
            and parsed_url.hostname in {"127.0.0.1", "localhost"}
            and parsed_url.port == 5432
            and parsed_url.path == "/jj_arena_ci"), "Only disposable local PostgreSQL 18 CI is allowed"
    test_db_name = "jj_economy_ci_" + uuid.uuid4().hex[:12]
    with psycopg.connect(original_url, autocommit=True) as raw:
        raw.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(test_db_name)))

    def cleanup_test_db():
        with psycopg.connect(original_url, autocommit=True) as raw:
            raw.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(test_db_name)))

    atexit.register(cleanup_test_db)
    os.environ["DATABASE_URL"] = urlunsplit(parsed_url._replace(path="/" + test_db_name))
else:
    os.environ.pop("DATABASE_URL", None)
    os.environ["JJ_DB_PATH"] = tempfile.mkdtemp(prefix="jj-point-economy-") + "/db.sqlite"
os.environ["JJ_ENABLE_DEMO_MEMBER"] = "0"

from fastapi.testclient import TestClient

import app
import admin_console


def main():
    db = app.db
    with db.connect() as con:
        def user(name, role="member", *, deleted=None, created="2026-10-01T00:00:00+00:00"):
            return db.insert_returning_id(
                con,
                """INSERT INTO users(name,email,password_hash,role,ranking_name,created_at,deleted_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (name, uuid.uuid4().hex, "unused", role, name, created, deleted),
            )

        admin = user("EconomyAdmin", "admin")
        player = user("EconomyA")
        other = user("EconomyB")
        gone = user("EconomyGone", deleted="2026-10-20T00:00:00+00:00")
        older = user("EconomyReused", deleted="2026-10-21T00:00:00+00:00")
        fresh = user("EconomyReused", created="2026-10-22T00:00:00+00:00")

        def entry(key, name, points, when):
            con.execute(
                """INSERT INTO entries(id,date,name,remaining,reentries,initial,points,
                   game,game_type,source,created_by,created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (key, when, name, 450 + points, 0, 450, points,
                 "ring", "ring", "test", admin, when + "+09:00"),
            )

        entry("econ-club-a", "EconomyA", 50, "2026-10-25T12:00:00")
        entry("econ-club-b", "EconomyB", -50, "2026-10-25T12:00:00")
        entry("econ-deleted-entry", "EconomyGone", 100, "2026-10-15T12:00:00")
        entry("econ-prior-generation", "EconomyReused", 200, "2026-10-10T12:00:00")
        entry("econ-new-generation", "EconomyReused", 4, "2026-10-25T12:00:00")
        entry("econ-operator", "運営調整", 1000, "2026-10-25T12:00:00")

        def hand(key, uid, points, *, voided=0, at="2026-10-24T15:45:00+00:00"):
            con.execute(
                """INSERT INTO online_hands(hand_id,table_id,hand_no,gross_pot_bb,rake_bb,
                   played_at,month,voided) VALUES (?,?,?,?,?,?,?,?)""",
                (key, "jj-table-a", 1, 100, 0, at, "2026-10", voided),
            )
            con.execute(
                """INSERT INTO online_hand_results(id,hand_id,table_id,user_id,ranking_name,
                   result_bb,points,month,created_at) VALUES (?,?,?,?,?,?,?,?,?)""",
                (key + "-result", key, "jj-table-a", uid,
                 "EconomyGone" if uid == gone else "EconomyA", 1, points, "2026-10", at),
            )

        hand("econ-online", player, 20)
        hand("econ-voided", player, 300, voided=1)
        hand("econ-deleted-hand", gone, 500)

        def ledger(key, uid, kind, points, reason):
            con.execute(
                """INSERT INTO point_ledger(id,user_id,amount,kind,reason,effective_at,
                   created_by,created_at,reversal_of) VALUES (?,?,?,?,?,?,?,?,NULL)""",
                (key, uid, points, kind, reason, "2026-10-24T15:30:00+00:00",
                 admin, "2026-10-24T15:30:00+00:00"),
            )

        ledger("econ-quiz", player, "quiz_reward", 10, "今日のクイズ")
        ledger("econ-other", player, "collection", -5, "管理者回収")
        ledger("econ-sng", player, "sitngo_prize", 12, "Sit&Go 賞金")
        ledger("econ-gone", gone, "quiz_reward", 100, "削除済み")

    client = TestClient(app.app, base_url="https://testserver", raise_server_exceptions=False)
    endpoint = "/api/admin/point-economy"
    assert client.get(endpoint).status_code == 401
    client.headers["Authorization"] = "Bearer " + db.create_session(player)
    assert client.get(endpoint).status_code == 403
    client.headers["Authorization"] = "Bearer " + db.create_session(admin)
    response = client.get(endpoint)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["totals"] == {"club": 4, "online": 20, "quiz": 10, "other": 7, "total": 41}, result["totals"]
    oct25 = next(row for row in result["daily"] if row["date"] == "2026-10-25")
    assert (oct25["club"], oct25["online"], oct25["quiz"], oct25["other"], oct25["cumulative"]) == (4, 20, 10, 7, 41), oct25
    assert not any(r["id"] in {"econ-deleted-entry", "econ-prior-generation", "econ-operator", "econ-deleted-hand-result", "econ-voided-result", "econ-gone"} for r in result["history"])
    assert sum(float(r["points"]) for r in admin_console._rankings(db, app.runtime_server)) == result["totals"]["total"]

    # A broken online aggregation must never produce a plausible-looking but
    # incorrect ranking with everyone else's online points set to zero.
    original_connect = db.connect

    @contextmanager
    def online_query_failure():
        with original_connect() as con:
            class FailingConnection:
                def execute(self, query, params=()):
                    if "FROM online_hand_results r JOIN online_hands h" in query:
                        raise RuntimeError("synthetic online ranking query failure")
                    return con.execute(query, params)

            yield FailingConnection()

    try:
        db.connect = online_query_failure
        try:
            admin_console._rankings(db, app.runtime_server)
        except RuntimeError as error:
            assert str(error) == "synthetic online ranking query failure"
        else:
            raise AssertionError("Ranking hid an online aggregation failure")
    finally:
        db.connect = original_connect

    # Filtered pagination never changes the full economy totals.
    first = client.get(endpoint, params={"source": "club", "limit": 1}).json()
    second = client.get(endpoint, params={"source": "club", "limit": 1, "offset": first["next_offset"]}).json()
    assert first["totals"] == result["totals"]
    assert first["history"][0]["id"] != second["history"][0]["id"]
    assert all(row["source"] == "club" for row in first["history"] + second["history"])
    assert [row["id"] for row in client.get(endpoint, params={"source": "quiz"}).json()["history"]] == ["econ-quiz"]
    assert client.get(endpoint, params={"source": "admin"}).status_code == 422
    assert client.get(endpoint, params={"limit": 999}).status_code == 422

    assert "JJ_POINT_ECONOMY_V1" not in app._patched_app_js()
    assert "jjPointEconomy" not in app._patched_index()
    assert ".jj-economy-grid" not in app._patched_styles()
    root = Path(__file__).resolve().parent / "admin_static"
    html = (root / "index.html").read_text(encoding="utf-8")
    js = (root / "admin_point_economy.js").read_text(encoding="utf-8")
    css = (root / "admin_point_economy.css").read_text(encoding="utf-8")
    admin_js = (root / "admin.js").read_text(encoding="utf-8")
    assert 'data-view="economy"' in html and 'id="economyView"' in html
    assert '/admin-static/admin_point_economy.js?v=1' in html
    assert '/admin-static/admin_point_economy.css?v=1' in html
    assert "window.jjLoadPointEconomy" in js and "jjLoadPointEconomy?.()" in admin_js
    assert "/admin/point-economy?" in js and ".economy-numbers" in css
    assert 'id="pointForm"' in html, "The official point input form must be preserved"
    assert client.get('/admin').status_code == 200
    assert client.get('/admin-static/admin_point_economy.js').status_code == 200
    assert client.get('/admin-static/admin_point_economy.css').status_code == 200
    backend = "POSTGRES" if "--postgres" in sys.argv else "SQLITE"
    print(f"JJ_POINT_ECONOMY_{backend}_OK attributed_totals jst deletions voids pagination auth admin-only-ui fail-closed-rankings")


if __name__ == "__main__":
    main()
