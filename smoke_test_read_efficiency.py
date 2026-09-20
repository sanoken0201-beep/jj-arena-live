"""Real DB parity, query counts, auth boundaries and broadcast privacy."""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import tempfile
import uuid


def main():
    if "--postgres" in sys.argv:
        # Never run mutating fixtures against a remote/production database.
        from psycopg.conninfo import conninfo_to_dict
        assert conninfo_to_dict(os.environ["DATABASE_URL"]).get("host") in {"localhost", "127.0.0.1"}
    else:
        os.environ["DATABASE_URL"] = ""
        os.environ["JJ_DB_PATH"] = str(Path(tempfile.mkdtemp(prefix="jj-reads-")) / "test.db")
    import app
    import runtime_performance
    from fastapi.testclient import TestClient
    db, server, engine = app.db, app.runtime_server, app.runtime_poker_engine
    original_connect = db.connect
    queries, connections = [], []

    class CountConnection:
        def __init__(self, con):
            self.con = con

        def __getattr__(self, name):
            return getattr(self.con, name)

        def execute(self, sql, params=()):
            queries.append(sql)
            return self.con.execute(sql, params)

    @contextmanager
    def counted_connect():
        connections.append(1)
        with original_connect() as con:
            yield CountConnection(con)

    db.connect = counted_connect
    suffix = uuid.uuid4().hex[:10]
    users = []
    with db.connect() as con:
        for i in range(6):
            uid = db.insert_returning_id(con,
                "INSERT INTO users(name,email,password_hash,role,xp,ranking_name,created_at) VALUES (?,?,?,?,?,?,?)",
                (f"Read-{suffix}-{i}" if i != 5 else "", f"read-{suffix}-{i}@test.invalid", "unused",
                 "admin" if i == 0 else "member", i, f"Rank-{suffix}-{i}" if i < 3 else None, db.utcnow()))
            users.append(uid)
    token, member_token = db.create_session(users[0]), db.create_session(users[1])
    client = TestClient(app.app)
    headers = {"Authorization": "Bearer " + token}

    def get(path, auth=headers):
        response = client.get(path, headers=auth)
        assert response.status_code == 200, (path, response.status_code, response.text)
        return response.json()

    def reset():
        queries.clear()
        connections.clear()

    def auth_count():
        return sum("FROM sessions s JOIN users" in query for query in queries)

    expected_me = server.user_payload(users[0])
    reset()
    assert get("/api/me") == expected_me
    assert len(queries) == auth_count() == len(connections) == 1, queries
    print("/me: 1 SELECT; exact legacy schema")

    for path, fields, legacy in (
        ("/api/home/core", ["rankings", "schedules", "announcements", "tables"],
         ["/api/rankings", "/api/schedules", "/api/announcements", "/api/tables"]),
        ("/api/points/dashboard", ["entries", "ranking_names"], ["/api/entries?limit=40", "/api/ranking-names"]),
    ):
        reset()
        expected = {key: get(url) for key, url in zip(fields, legacy)}
        old_auth, old_connections = auth_count(), len(connections)
        reset()
        assert get(path) == expected
        assert auth_count() == 1 and len(connections) == 2, (queries, connections)
        print(f"{path}: auth {old_auth}->1; connections {old_connections}->2; exact legacy payload")
        assert client.get(path).status_code == 401
        expected_member_status = 403 if path == "/api/points/dashboard" else 200
        assert client.get(path, headers={"Authorization": "Bearer " + member_token}).status_code == expected_member_status
    assert client.post("/api/entries", headers={"Authorization": "Bearer " + member_token}, json={}).status_code == 403
    with db.connect() as con:
        con.execute("UPDATE users SET disabled=1 WHERE id=?", (users[1],))
    for path in ("/api/me", "/api/home/core", "/api/points/dashboard"):
        assert client.get(path, headers={"Authorization": "Bearer " + member_token}).status_code == 403

    # Execute both settlement paths under savepoints with identical clock/input.
    hand = {"id": "read-" + suffix, "phase": "complete"}
    state = {"id": db.FIXED_TABLES[0][0], "hand": hand, "hand_no": 7, "big_blind": 100,
             "last_result": {"gross_pot": 12345, "rake": 500, "net_results": [
                 {"user_id": uid, "name": f"Fallback-{i}", "amount": amount}
                 for i, (uid, amount) in enumerate(zip(users, [-15000, 213, 6000, -1213, 10000, -500]))]}}
    old_now, old_month = db.utcnow, db.japan_month
    db.utcnow, db.japan_month = lambda: "2026-09-15T12:00:00+00:00", lambda: "2026-09"
    outcomes = []
    try:
        with db.connect() as con:
            for function in (db._record_online_hand.__wrapped__, db._record_online_hand):
                con.execute("SAVEPOINT settlement_parity")
                reset()
                result = function(con, deepcopy(state))
                user_reads = sum("FROM users WHERE id" in q for q in queries)
                rows = con.execute("SELECT * FROM online_hand_results WHERE hand_id=? ORDER BY id", (hand["id"],)).fetchall()
                outcomes.append((result, [dict(row) for row in rows], user_reads))
                # Idempotency must also remain intact.
                assert function(con, deepcopy(state)) == result
                assert len(con.execute("SELECT id FROM online_hand_results WHERE hand_id=?", (hand["id"],)).fetchall()) == 6
                con.execute("ROLLBACK TO SAVEPOINT settlement_parity")
                con.execute("RELEASE SAVEPOINT settlement_parity")
        assert outcomes[0][:2] == outcomes[1][:2]
        assert (outcomes[0][2], outcomes[1][2]) == (6, 1), outcomes
        assert outcomes[1][0]["results"][-1]["ranking_name"] == "Fallback-5"
        print("settlement: user SELECT 6->1; points/names/persisted rows/idempotency identical")
    finally:
        db.utcnow, db.japan_month = old_now, old_month

    class WS:
        def __init__(self):
            self.frames = []

        async def send_json(self, payload):
            self.frames.append(json.loads(json.dumps(payload)))

    async def broadcast_checks():
        tid = db.FIXED_TABLES[0][0]
        runtime_performance._LAST_BROADCAST_STATE.clear()
        state = server.load_table(tid)
        state["seats"] = []
        for i, uid in enumerate(users):
            engine.seat_player(state, user_id=uid, name=f"Player-{i}", seat=i, stack=15000)
        engine.start_hand(state)
        server.arm_action_deadline(state)
        sockets = [WS() for _ in users]
        server.hub.connections[tid] = list(zip(sockets, users))
        reset()
        server.save_table(state)
        saved_state = deepcopy(state)
        server._jj_v16_repair_table_state(saved_state)
        # Mutations after save must not leak into the private cache or frames.
        state["seats"][0]["stack"] += 777
        await server.hub.broadcast(tid)
        assert not any("SELECT state_json FROM tables" in q for q in queries), queries
        for uid, ws in zip(users, sockets):
            assert ws.frames[-1]["state"] == json.loads(json.dumps(engine.public_state(saved_state, uid)))
            assert "deck" not in ws.frames[-1]["state"]["hand"]
            for seat in ws.frames[-1]["state"]["seats"]:
                if seat["user_id"] != uid:
                    assert seat["cards"] == ["??", "??"]
        print("broadcast after committed save: 0 table SELECT; 6 personalized private-card-safe frames")

        # A fresh load (chat path) primes a one-turn snapshot without a write.
        reset()
        server.load_table(tid)
        await server.hub.broadcast(tid)
        assert sum("SELECT state_json FROM tables" in q for q in queries) == 1
        assert sockets[0].frames[-1]["type"] == "chat"

        unchanged = server.load_table(tid)
        server.save_table(unchanged)
        await server.hub.broadcast(tid)
        assert sockets[0].frames[-1]["type"] == "chat", "no-op saves must preserve frame selection"

        # A restored/missing snapshot cannot be used with an old generation.
        server.load_table(tid)
        server._jj_broadcast_snapshots.snapshots.clear()
        reset()
        await server.hub.broadcast(tid)
        assert sum("SELECT state_json FROM tables" in q for q in queries) == 1

        # Once execution yields, the old ticket must no longer skip DB reads.
        server.load_table(tid)
        await asyncio.sleep(0)
        reset()
        await server.hub.broadcast(tid)
        assert sum("SELECT state_json FROM tables" in q for q in queries) == 1

        # Inherited ContextVars must not allow a child task to reuse the ticket.
        server.load_table(tid)
        reset()
        await asyncio.create_task(server.hub.broadcast(tid))
        assert sum("SELECT state_json FROM tables" in q for q in queries) == 1

        # Failed DB persistence must neither publish uncommitted state nor hide
        # the authoritative fallback. Includes rollback during hand settlement.
        good = server.load_table(tid)
        bad = deepcopy(good)
        bad["hand"]["phase"] = "complete"
        bad["hand"].pop("result_persisted", None)
        bad["name"] = None  # tables.name NOT NULL, after settlement attempt
        bad["last_result"] = state.get("last_result") or {"net_results": []}
        try:
            server.save_table(bad)
            raise AssertionError("expected DB failure")
        except (AssertionError,):
            raise
        except Exception:
            pass
        reset()
        await server.hub.broadcast(tid)
        assert sum("SELECT state_json FROM tables" in q for q in queries) == 1
        assert server.load_table(tid) == good
        with db.connect() as con:
            assert con.execute("SELECT hand_id FROM online_hands WHERE hand_id=?", (good["hand"]["id"],)).fetchone() is None
        print("chat separation, await expiry, commit rollback and authoritative fallback passed")
        server.hub.connections.clear()

    asyncio.run(broadcast_checks())
    print("READ_EFFICIENCY_OK", "postgres" if db.IS_POSTGRES else "sqlite")


if __name__ == "__main__":
    if "--postgres" not in sys.argv:
        main()
    else:
        import psycopg
        from psycopg import sql
        from psycopg.conninfo import conninfo_to_dict, make_conninfo
        original_url = os.environ["DATABASE_URL"]
        assert conninfo_to_dict(original_url).get("host") in {"localhost", "127.0.0.1"}
        database = "jj_read_test_" + uuid.uuid4().hex[:12]
        with psycopg.connect(original_url, autocommit=True) as control:
            control.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
            try:
                os.environ["DATABASE_URL"] = make_conninfo(original_url, dbname=database)
                main()
            finally:
                import runtime_performance
                if runtime_performance._POOL:
                    runtime_performance._POOL.close()
                control.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database)))
