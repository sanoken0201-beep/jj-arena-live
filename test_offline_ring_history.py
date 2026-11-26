"""Regression coverage for the read-only offline ring history."""
import sqlite3
from contextlib import contextmanager
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import offline_ring_history as ring
import season_management


class DB:
    def __init__(self):
        self.con = sqlite3.connect(":memory:", check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.con.executescript("""
          CREATE TABLE users(id INTEGER PRIMARY KEY, name TEXT);
          INSERT INTO users VALUES(1,'operator');
          CREATE TABLE entries(id TEXT PRIMARY KEY,date TEXT,name TEXT,game TEXT,
            game_type TEXT,initial INTEGER,reentries INTEGER,remaining INTEGER,
            points INTEGER,created_at TEXT,created_by INTEGER);
        """)
        for id, day, name, kind, initial, points in [
            ("a", "2026-11-26T19:30", "A", "ring", 1000, -50),
            ("b", "2026-11-26T19:30", "B", "ring", 3000, 50),
            ("c", "2026-10-01", "A", "ring", 900, 100),
            ("d", "2026-11-26", "A", "tournament", 400, 200),
            ("e", "2026-11-26", "運営調整", "ring", 1000, 200),
            ("f", "2026-07-01", "A", "ring", 450, 0),
            ("g", "2026-11-25", "100%", "ring", 1000, 0),
        ]:
            self.con.execute("INSERT INTO entries VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (id,day,name,str(initial)+" / blind",kind,initial,0,initial+points,
                 points,"2026-11-26T12:00:00Z",1))
        self.con.commit()

    @contextmanager
    def connect(self):
        yield self.con


def test_ring_filter_pagination_and_stored_points():
    db = DB()
    result = ring.history(db, start="2026-09-01", end="2027-04-01", limit=1)
    assert [e["id"] for e in result["entries"]] == ["b"]
    assert result["next_offset"] == 1
    assert "entered_by" not in result["entries"][0]
    assert [e["id"] for e in ring.history(db,start="2026-09-01",offset=1,limit=1)["entries"]] == ["a"]
    historical = ring.history(db, player="A", initial=900, admin=True)["entries"]
    assert historical[0]["id"] == "c"
    assert historical[0]["points"] == 100
    assert historical[0]["entered_by"] == "operator"
    assert [e["id"] for e in ring.history(db, player="%")["entries"]] == ["g"]
    assert [e["id"] for e in ring.history(db,date_from="2026-11-26",date_to="2026-11-26")["entries"]] == ["b","a"]
    assert {e["id"] for e in ring.history(db)["entries"]} == {"a","b","c","f","g"}
    assert db.con.execute("SELECT COUNT(*) FROM entries").fetchone()[0] == 7


def test_route_permissions_and_validation(monkeypatch):
    monkeypatch.setattr(season_management, "bounds", lambda db, season: ("2026-09-01","2027-04-01"))
    db = DB()
    state = {"role": None}

    def user():
        if not state["role"]:
            raise HTTPException(401)
        return {"role": state["role"]}

    app = FastAPI()
    ring.install(app, SimpleNamespace(current_user=user), db)
    client = TestClient(app)
    path = "/api/points/ring-history"
    assert client.get(path).status_code == 401
    state["role"] = "member"
    assert client.get(path+"?archive=true").status_code == 403
    assert client.get(path+"?limit=101").status_code == 422
    assert client.get(path+"?date_from=2026-11-26&date_to=2026-11-25").status_code == 400
    member = client.get(path).json()["entries"]
    assert {e["id"] for e in member} == {"a","b","c","g"}
    assert all("entered_by" not in e for e in member)
    state["role"] = "admin"
    admin = client.get(path+"?archive=true").json()["entries"]
    assert {e["id"] for e in admin} == {"a","b","c","f","g"}
    assert all(e["entered_by"] == "operator" for e in admin)


def test_transform_hooks_existing_point_view():
    source = "  async function renderPoints(){$('#recentEntries').innerHTML=ents.map(row)}\n  const pointDenoms=[]"
    result = ring.transform_app_js(source)
    assert ring.MARKER in result
    assert "jjInitRingHistory();" in result
    assert "/points/ring-history?" in result
    assert "URLSearchParams" in result
