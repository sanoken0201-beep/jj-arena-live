"""Ring admin buy-ins and rakeback settlement stay authorized and append-only."""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from pathlib import Path

os.environ.pop("DATABASE_URL", None)
os.environ["JJ_DB_PATH"] = tempfile.mkdtemp(prefix="jj-ring-admin-") + "/test.db"
os.environ["JJ_ENABLE_DEMO_MEMBER"] = "0"

import app as production
from fastapi.testclient import TestClient


def _client(token: str) -> TestClient:
    client = TestClient(
        production.app,
        base_url="https://testserver",
        raise_server_exceptions=False,
    )
    client.headers["Authorization"] = "Bearer " + token
    return client


def _insert_user(db, role: str, name: str) -> int:
    with db.connect() as con:
        return db.insert_returning_id(
            con,
            """INSERT INTO users(
                 name,email,password_hash,role,arena_chips,xp,approved,disabled,
                 ranking_name,created_at
               ) VALUES (?,?,?,?,0,0,1,0,?,?)""",
            (name, uuid.uuid4().hex, "unused", role, name, db.utcnow()),
        )


def _stack_for(server, table_id: str, user_id: int) -> int:
    state = server.load_table(table_id)
    player = next(p for p in state["seats"] if int(p["user_id"]) == int(user_id))
    return int(player["stack"])


def _insert_hand(db, hand_id: str, hand_no: int, rake_bb: float, *, voided: int = 0) -> None:
    with db.connect() as con:
        con.execute(
            """INSERT INTO online_hands(
                 hand_id,table_id,hand_no,gross_pot_bb,rake_bb,played_at,month,voided
               ) VALUES (?,?,?,?,?,?,?,?)""",
            (
                hand_id,
                "jj-table-a",
                hand_no,
                20,
                rake_bb,
                db.utcnow(),
                "2026-10",
                voided,
            ),
        )


def main() -> None:
    db, server = production.db, production.runtime_server
    admin_id = _insert_user(db, "admin", "Ring Admin")
    member_ids = [
        _insert_user(db, "member", "Ring Member A"),
        _insert_user(db, "member", "Ring Member B"),
        _insert_user(db, "member", "Ring Member C"),
        _insert_user(db, "member", "Ring Member D"),
    ]
    admin = _client(db.create_session(admin_id))
    members = [_client(db.create_session(uid)) for uid in member_ids]

    initial = admin.get("/api/admin/console/ring")
    assert initial.status_code == 200, initial.text
    assert initial.json()["min_buyin_bb"] == 150
    assert initial.json()["max_buyin_bb"] == 150

    assert members[0].get("/api/admin/console/ring").status_code == 403
    assert members[0].patch(
        "/api/admin/console/ring",
        json={"min_buyin_bb": 50, "max_buyin_bb": 200},
    ).status_code == 403
    assert members[0].post("/api/admin/console/ring/rake-reset", json={}).status_code == 403

    bad = admin.patch(
        "/api/admin/console/ring",
        json={"min_buyin_bb": 250, "max_buyin_bb": 200},
    )
    assert bad.status_code == 400, bad.text

    changed = admin.patch(
        "/api/admin/console/ring",
        json={"min_buyin_bb": 50, "max_buyin_bb": 200},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["min_buyin_bb"] == 50
    assert changed.json()["max_buyin_bb"] == 200

    with db.connect() as con:
        state = json.loads(
            con.execute(
                "SELECT state_json FROM tables WHERE id='jj-table-a'"
            ).fetchone()["state_json"]
        )
    assert int(state["min_buyin"]) == 5000
    assert int(state["max_buyin"]) == 20000

    listing = members[0].get("/api/tables")
    assert listing.status_code == 200, listing.text
    assert len(listing.json()) == 1
    assert listing.json()[0]["min_buyin_bb"] == 50
    assert listing.json()[0]["max_buyin_bb"] == 200

    joined = members[0].post(
        "/api/tables/jj-table-a/join",
        json={"buyin_bb": 100},
    )
    assert joined.status_code == 200, joined.text
    assert _stack_for(server, "jj-table-a", member_ids[0]) == 10000

    too_low = members[1].post(
        "/api/tables/jj-table-a/seat",
        json={"seat": 1, "buyin_bb": 40},
    )
    assert too_low.status_code == 400, too_low.text

    seated = members[1].post(
        "/api/tables/jj-table-a/seat",
        json={"seat": 1, "buyin_bb": 120},
    )
    assert seated.status_code == 200, seated.text
    assert _stack_for(server, "jj-table-a", member_ids[1]) == 12000

    # Rebuy must use the same configured range.
    state = server.load_table("jj-table-a")
    player = next(p for p in state["seats"] if int(p["user_id"]) == member_ids[1])
    player["stack"] = 0
    server.save_table(state)
    rebuy = members[1].post(
        "/api/tables/jj-table-a/presence",
        json={"mode": "rebuy", "buyin_bb": 180},
    )
    assert rebuy.status_code == 200, rebuy.text
    assert _stack_for(server, "jj-table-a", member_ids[1]) == 18000

    # A stale client that omits buyin_bb keeps working using the clamped 150bb default.
    stale = members[2].post("/api/tables/jj-table-a/join")
    assert stale.status_code == 200, stale.text
    assert _stack_for(server, "jj-table-a", member_ids[2]) == 15000

    # Tightening the range never rewrites existing seated stacks.
    tightened = admin.patch(
        "/api/admin/console/ring",
        json={"min_buyin_bb": 80, "max_buyin_bb": 100},
    )
    assert tightened.status_code == 200, tightened.text
    assert _stack_for(server, "jj-table-a", member_ids[1]) == 18000
    assert _stack_for(server, "jj-table-a", member_ids[2]) == 15000
    new_default = members[3].post("/api/tables/jj-table-a/join")
    assert new_default.status_code == 200, new_default.text
    assert _stack_for(server, "jj-table-a", member_ids[3]) == 10000

    _insert_hand(db, "ring-rake-1", 9001, 1.25)
    _insert_hand(db, "ring-rake-2", 9002, 0.75)
    rake = admin.get("/api/admin/console/ring").json()["rake"]
    assert rake["current"] == {"rake_bb": 2.0, "rake_points": 200.0, "hands": 2}
    assert rake["all_time"]["rake_points"] == 200.0

    reset = admin.post("/api/admin/console/ring/rake-reset", json={})
    assert reset.status_code == 200, reset.text
    payload = reset.json()["rake"]
    assert payload["current"]["rake_points"] == 0.0
    assert payload["last_reset"]["settled_rake_points"] == 200.0
    assert payload["last_reset"]["hand_count"] == 2

    # Reset is a settlement boundary, not deletion. New hands begin a fresh balance.
    _insert_hand(db, "ring-rake-3", 9003, 0.50)
    _insert_hand(db, "ring-rake-void", 9004, 1.00, voided=1)
    current = admin.get("/api/admin/console/ring").json()["rake"]
    assert current["current"]["rake_points"] == 50.0
    assert current["current"]["hands"] == 1
    assert current["all_time"]["rake_points"] == 250.0

    second = admin.post("/api/admin/console/ring/rake-reset", json={})
    assert second.status_code == 200, second.text
    assert second.json()["rake"]["current"]["rake_points"] == 0.0
    assert admin.post("/api/admin/console/ring/rake-reset", json={}).status_code == 409

    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) n FROM online_hands").fetchone()["n"] == 4
        assert con.execute("SELECT COUNT(*) n FROM ring_rake_settlements").fetchone()["n"] == 2
        assert con.execute(
            "SELECT COUNT(*) n FROM admin_audit_log WHERE action='ring.settings.update'"
        ).fetchone()["n"] == 2
        assert con.execute(
            "SELECT COUNT(*) n FROM admin_audit_log WHERE action='ring.rake.reset'"
        ).fetchone()["n"] == 2

    js = production._patched_app_js()
    assert "ring variable buy-in ui 2026-10-05" in js
    assert "buyin_bb" in js
    html = (Path(__file__).resolve().parent / "admin_static" / "index.html").read_text(
        encoding="utf-8"
    )
    for marker in ("ringBuyinForm", "ringRakeCurrentPoints", "ringRakeReset"):
        assert marker in html

    print(
        "JJ_RING_ADMIN_CONFIG_OK auth=ok buyin=50-200 rebuy=180 "
        "existing_stacks=preserved rake_reset=append-only"
    )


if __name__ == "__main__":
    main()
