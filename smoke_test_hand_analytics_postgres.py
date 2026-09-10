from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from runtime_builder import build_runtime


def run() -> None:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        raise AssertionError("DATABASE_URL is required for PostgreSQL smoke test")

    runtime = build_runtime(Path(tempfile.mkdtemp(prefix="jj-pg-analytics-")) / "runtime")
    previous = {k: os.environ.get(k) for k in ("JJ_ADMIN_NAME", "JJ_ADMIN_PIN", "JJ_ENABLE_DEMO_MEMBER")}
    os.environ["JJ_ADMIN_NAME"] = "ケンイチロウ"
    os.environ["JJ_ADMIN_PIN"] = "654321"
    os.environ["JJ_ENABLE_DEMO_MEMBER"] = "0"

    old_modules = {}
    for name in ("db", "server", "poker_engine"):
        if name in sys.modules:
            old_modules[name] = sys.modules.pop(name)
    sys.path.insert(0, str(runtime))
    try:
        import db  # type: ignore
        import poker_engine  # type: ignore
        import server  # type: ignore
        import hand_analytics
        import hand_analytics_hardening

        assert db.IS_POSTGRES is True
        hand_analytics.install(server.app, server, db)
        hand_analytics_hardening.install(hand_analytics, server)

        expected_tables = {
            "jj_hand_history",
            "jj_hand_players",
            "jj_hand_actions",
            "jj_hand_snapshots",
            "jj_hand_reviews",
        }
        with db.connect() as con:
            rows = con.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name LIKE 'jj_hand_%'"
            ).fetchall()
            found = {str(row["table_name"]) for row in rows}
            assert expected_tables <= found, (expected_tables, found)

            def make_user(name: str) -> int:
                login = f"pg-smoke-{name}@jj.invalid"
                existing = con.execute("SELECT id FROM users WHERE email=?", (login,)).fetchone()
                if existing:
                    return int(existing["id"])
                return db.insert_returning_id(
                    con,
                    """INSERT INTO users(
                         name,email,password_hash,role,arena_chips,xp,approved,disabled,ranking_name,created_at
                       ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (name, login, db.hash_password("123456"), "member", 0, 0, 1, 0, name, db.utcnow()),
                )

            alice = make_user("アリスPG")
            bob = make_user("ボブPG")

        state = poker_engine.blank_table_state(
            table_id="jj-table-a",
            name="JJ Table A",
            max_seats=6,
            small_blind=50,
            big_blind=100,
            min_buyin=15000,
            max_buyin=15000,
        )
        poker_engine.seat_player(state, user_id=alice, name="アリスPG", seat=0, stack=15000)
        poker_engine.seat_player(state, user_id=bob, name="ボブPG", seat=1, stack=15000)
        for player in state["seats"]:
            player["ready"] = True
            player["sitting_out"] = False
            player["sit_out_next"] = False

        # Reconstructed server/engine path: start, persist, act, persist.
        server.start_hand(state)
        hand_id = str(state["hand"]["id"])
        server.arm_action_deadline(state)
        server.save_table(state)
        assert state["hand"]["action_seat"] == 0
        server.apply_action(state, alice, "fold", None)
        server.save_table(state)
        assert state["hand"]["phase"] == "complete"

        with db.connect() as con:
            hand = con.execute(
                "SELECT hand_id,completed_at,partial_capture,result_type FROM jj_hand_history WHERE hand_id=?",
                (hand_id,),
            ).fetchone()
            assert hand is not None
            assert hand["completed_at"]
            assert int(hand["partial_capture"] or 0) == 0
            assert str(hand["result_type"]) == "uncontested"

            players = con.execute(
                "SELECT user_id,position,net_bb,vpip,pfr FROM jj_hand_players WHERE hand_id=? ORDER BY seat",
                (hand_id,),
            ).fetchall()
            assert len(players) == 2
            by_uid = {int(row["user_id"]): dict(row) for row in players}
            assert by_uid[alice]["position"] == "BTN/SB"
            assert float(by_uid[alice]["net_bb"]) == -0.5
            assert float(by_uid[bob]["net_bb"]) == 0.5

            actions = con.execute(
                "SELECT user_id,street,action FROM jj_hand_actions WHERE hand_id=? ORDER BY seq",
                (hand_id,),
            ).fetchall()
            assert len(actions) == 1
            assert int(actions[0]["user_id"]) == alice
            assert actions[0]["street"] == "preflop"
            assert actions[0]["action"] == "fold"

            snapshots = con.execute(
                "SELECT state_json FROM jj_hand_snapshots WHERE hand_id=? ORDER BY seq",
                (hand_id,),
            ).fetchall()
            assert snapshots
            assert all('"deck"' not in str(row["state_json"]) for row in snapshots)

        summary_alice = hand_analytics._summary_payload(alice, "all", None)
        summary_bob = hand_analytics._summary_payload(bob, "all", None)
        assert summary_alice["overall"]["hands"] >= 1
        assert summary_bob["overall"]["hands"] >= 1
        assert summary_alice["overall"]["net_bb"] <= -0.5
        assert summary_bob["overall"]["net_bb"] >= 0.5

        # Analytics API privacy: each participant may open the hand, but the
        # opponent's uncontested/mucked cards remain hidden.
        alice_detail = hand_analytics._detail_payload(hand_id, alice)
        alice_cards = {int(p["user_id"]): p["cards"] for p in alice_detail["players"]}
        assert len(alice_cards[alice]) == 2
        assert alice_cards[bob] == ["??", "??"]

        # Live public-state privacy is independently hardened too.
        public_for_alice = poker_engine.public_state(state, alice)
        public_cards = {int(p["user_id"]): list(p.get("cards") or []) for p in public_for_alice["seats"]}
        assert len(public_cards[alice]) == 2
        assert public_cards[bob] == []

        print("JJ_HAND_ANALYTICS_POSTGRES_SMOKE_OK")
    finally:
        if str(runtime) in sys.path:
            sys.path.remove(str(runtime))
        for name in ("db", "server", "poker_engine"):
            sys.modules.pop(name, None)
        sys.modules.update(old_modules)
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


if __name__ == "__main__":
    run()
