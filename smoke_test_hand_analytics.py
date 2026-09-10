from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from fastapi import HTTPException

from runtime_builder import build_runtime


def _route(app, path: str, method: str):
    method = method.upper()
    for route in app.router.routes:
        if getattr(route, "path", None) == path and method in (getattr(route, "methods", None) or set()):
            return route
    raise AssertionError(f"route missing: {method} {path}")


def _clear_runtime_modules() -> dict[str, object]:
    names = ["db", "server", "poker_engine"]
    old = {}
    for name in names:
        if name in sys.modules:
            old[name] = sys.modules.pop(name)
    return old


def run() -> None:
    work = Path(tempfile.mkdtemp(prefix="jj-hand-analytics-smoke-"))
    runtime = build_runtime(work / "runtime")
    db_path = work / "analytics.sqlite3"
    previous = {k: os.environ.get(k) for k in (
        "DATABASE_URL", "JJ_DB_PATH", "JJ_ADMIN_NAME", "JJ_ADMIN_PIN", "JJ_ENABLE_DEMO_MEMBER"
    )}
    old_modules = _clear_runtime_modules()
    os.environ.pop("DATABASE_URL", None)
    os.environ["JJ_DB_PATH"] = str(db_path)
    os.environ["JJ_ADMIN_NAME"] = "ケンイチロウ"
    os.environ["JJ_ADMIN_PIN"] = "654321"
    os.environ["JJ_ENABLE_DEMO_MEMBER"] = "0"
    sys.path.insert(0, str(runtime))
    try:
        import db  # type: ignore
        import server  # type: ignore
        import poker_engine  # type: ignore
        import hand_analytics

        hand_analytics.install(server.app, server, db)
        assert getattr(server, "_jj_hand_analytics_wrapped", False)

        with db.connect() as con:
            def create_user(name: str) -> int:
                email = f"test-{name}@jj.invalid"
                return db.insert_returning_id(
                    con,
                    "INSERT INTO users(name,email,password_hash,role,arena_chips,xp,created_at) VALUES (?,?,?,?,?,?,?)",
                    (name, email, db.hash_password("123456"), "member", 0, 0, db.utcnow()),
                )
            u1, u2, u3, outsider = (
                create_user("アリス"), create_user("ボブ"), create_user("キャロル"), create_user("アウトサイダー")
            )

        state = poker_engine.blank_table_state(
            table_id="jj-table-a", name="JJ Table A", max_seats=6,
            small_blind=50, big_blind=100, min_buyin=15000, max_buyin=15000,
        )
        poker_engine.seat_player(state, user_id=u1, name="アリス", seat=0, stack=15000)
        poker_engine.seat_player(state, user_id=u2, name="ボブ", seat=1, stack=15000)
        poker_engine.seat_player(state, user_id=u3, name="キャロル", seat=2, stack=15000)
        for p in state["seats"]:
            p["ready"] = True
            p["sitting_out"] = False
            p["sit_out_next"] = False

        # Use the real reconstructed engine, but the analytics-wrapped server globals.
        server.start_hand(state)
        hand1 = str(state["hand"]["id"])
        server.save_table(state)
        assert state["hand"]["action_seat"] == 0, state["hand"]
        server.apply_action(state, u1, "raise", 300)
        server.save_table(state)
        server.apply_action(state, u2, "fold", None)
        server.save_table(state)
        server.apply_action(state, u3, "fold", None)
        server.save_table(state)
        assert state["hand"]["phase"] == "complete"

        with db.connect() as con:
            h = dict(con.execute("SELECT * FROM jj_hand_history WHERE hand_id=?", (hand1,)).fetchone())
            p1 = dict(con.execute("SELECT * FROM jj_hand_players WHERE hand_id=? AND user_id=?", (hand1, u1)).fetchone())
            p2 = dict(con.execute("SELECT * FROM jj_hand_players WHERE hand_id=? AND user_id=?", (hand1, u2)).fetchone())
            actions = [dict(r) for r in con.execute("SELECT * FROM jj_hand_actions WHERE hand_id=? ORDER BY seq", (hand1,)).fetchall()]
            snaps = [dict(r) for r in con.execute("SELECT * FROM jj_hand_snapshots WHERE hand_id=? ORDER BY seq", (hand1,)).fetchall()]
        assert h["completed_at"] and h["result_type"] == "uncontested"
        assert int(h["partial_capture"]) == 0
        assert p1["position"] == "BTN"
        assert int(p1["vpip"]) == 1 and int(p1["pfr"]) == 1
        assert int(p1["steal_opp"]) == 1 and int(p1["steal_attempt"]) == 1
        assert int(p2["vpip"]) == 0
        assert [a["action"] for a in actions] == ["raise", "fold", "fold"]
        assert all('"deck"' not in s["state_json"] for s in snaps)

        # Privacy: hero sees own cards; folded opponents remain hidden.
        detail = hand_analytics._detail_payload(hand1, u1)
        cards = {int(p["user_id"]): p["cards"] for p in detail["players"]}
        assert cards[u1] != ["??", "??"]
        assert cards[u2] == ["??", "??"]
        assert cards[u3] == ["??", "??"]
        try:
            hand_analytics._detail_payload(hand1, outsider)
        except HTTPException as exc:
            assert exc.status_code == 404
        else:
            raise AssertionError("unrelated user could read another player's hand")

        export = hand_analytics._export_text(hand1, u1)
        assert export.startswith("JJ Arena Hand #")
        assert "*** HOLE CARDS ***" in export and "*** SUMMARY ***" in export
        assert "PokerStars-style text export" in export
        assert "Dealt to アリス" in export
        assert "ボブ: shows" not in export and "キャロル: shows" not in export

        # Directly create a showdown hand to verify disclosed-card visibility rules.
        showdown = {
            "id": "jj-table-b", "name": "JJ Table B", "max_seats": 6,
            "small_blind": 50, "big_blind": 100, "button_seat": 0, "hand_no": 50,
            "status": "playing",
            "seats": [
                {"user_id": u1, "name": "アリス", "seat": 0, "stack": 14950, "contributed": 50, "round_bet": 50, "cards": ["As", "Kd"], "in_hand": True, "folded": False, "all_in": False},
                {"user_id": u2, "name": "ボブ", "seat": 1, "stack": 14900, "contributed": 100, "round_bet": 100, "cards": ["Qc", "Qd"], "in_hand": True, "folded": False, "all_in": False},
            ],
            "hand": {"id": "jj-table-b-50", "phase": "preflop", "board": [], "current_bet": 100, "min_raise": 100, "acted": [], "action_seat": 0, "small_blind_seat": 0, "big_blind_seat": 1, "log": ["Hand #50 started"], "showdown": None},
        }
        hand_analytics._observe_state(showdown)
        showdown["status"] = "waiting"
        showdown["hand"]["phase"] = "complete"
        showdown["hand"]["board"] = ["2c", "7d", "Kh", "3s", "9c"]
        showdown["hand"]["showdown"] = {"scores": {str(u1): [1], str(u2): [2]}, "pots": []}
        showdown["last_result"] = {"type": "showdown", "winners": [{"user_id": u2, "name": "ボブ", "amount": 200}], "board": showdown["hand"]["board"], "message": "ボブ wins"}
        showdown["seats"][0].update(stack=14900, contributed=0, round_bet=0, in_hand=False)
        showdown["seats"][1].update(stack=15100, contributed=0, round_bet=0, in_hand=False)
        hand_analytics._observe_state(showdown)
        detail2 = hand_analytics._detail_payload("jj-table-b-50", u1)
        cards2 = {int(p["user_id"]): p["cards"] for p in detail2["players"]}
        assert cards2[u2] == ["Qc", "Qd"]

        # Review metadata is private to the participating user.
        review_ep = _route(server.app, "/api/analysis/hands/{hand_id}/review", "PUT").endpoint
        saved = review_ep(
            hand_id=hand1,
            payload=hand_analytics.HandReviewIn(bookmarked=True, note="BTN open review", tags=["steal", " review ", "steal"]),
            user={"id": u1, "name": "アリス"},
        )
        assert saved["bookmarked"] is True and saved["tags"] == ["steal", "review"]
        detail = hand_analytics._detail_payload(hand1, u1)
        assert detail["review"]["note"] == "BTN open review" and detail["review"]["bookmarked"] is True

        # Partial captures are visible as history but excluded from aggregate stats.
        partial = {
            "id": "jj-table-b", "name": "JJ Table B", "max_seats": 6,
            "small_blind": 50, "big_blind": 100, "button_seat": 0, "hand_no": 51,
            "status": "playing",
            "seats": [
                {"user_id": u1, "name": "アリス", "seat": 0, "stack": 14600, "contributed": 400, "round_bet": 0, "cards": ["Ah", "Ad"], "in_hand": True, "folded": False, "all_in": False},
                {"user_id": u2, "name": "ボブ", "seat": 1, "stack": 14600, "contributed": 400, "round_bet": 0, "cards": ["Ks", "Kc"], "in_hand": True, "folded": False, "all_in": False},
            ],
            "hand": {"id": "jj-table-b-51", "phase": "flop", "board": ["2s", "3s", "4d"], "current_bet": 0, "min_raise": 100, "acted": [], "action_seat": 1, "small_blind_seat": 0, "big_blind_seat": 1, "log": ["Hand #51 started", "アリス raises", "ボブ calls", "FLOP"], "showdown": None},
        }
        hand_analytics._observe_state(partial)
        partial["status"] = "waiting"
        partial["hand"]["phase"] = "complete"
        partial["last_result"] = {"type": "uncontested", "winners": [{"user_id": u1, "name": "アリス", "amount": 800}], "board": partial["hand"]["board"], "message": "アリス wins"}
        partial["seats"][0].update(stack=15400, contributed=0, in_hand=False)
        partial["seats"][1].update(stack=14600, contributed=0, in_hand=False)
        hand_analytics._observe_state(partial)
        with db.connect() as con:
            pr = con.execute("SELECT partial_capture FROM jj_hand_history WHERE hand_id='jj-table-b-51'").fetchone()
        assert int(pr["partial_capture"]) == 1
        complete_rows = hand_analytics._completed_player_rows(u1, "all")
        assert "jj-table-b-51" not in {r["hand_id"] for r in complete_rows}
        assert hand1 in {r["hand_id"] for r in complete_rows}

        summary = hand_analytics._summary_payload(u1, "all", None)
        assert summary["overall"]["hands"] >= 2
        assert "vpip" in summary["overall"] and "positions" in summary and "stack_bands" in summary
        assert summary["overall"]["bb_per_100"] is not None

        for path, method in [
            ("/api/analysis/summary", "GET"), ("/api/analysis/hands", "GET"),
            ("/api/analysis/hands/{hand_id}", "GET"), ("/api/analysis/hands/{hand_id}/review", "PUT"),
            ("/api/analysis/sessions", "GET"), ("/api/analysis/hands/{hand_id}/export.txt", "GET"),
            ("/api/analysis/export.csv", "GET"),
        ]:
            _route(server.app, path, method)

        print("JJ_HAND_ANALYTICS_SMOKE_OK")
    finally:
        if str(runtime) in sys.path:
            sys.path.remove(str(runtime))
        for name in ["db", "server", "poker_engine"]:
            sys.modules.pop(name, None)
        sys.modules.update(old_modules)
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


if __name__ == "__main__":
    run()
