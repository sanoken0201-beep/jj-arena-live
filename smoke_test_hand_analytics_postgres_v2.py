from __future__ import annotations

import os
import sys
import tempfile
import uuid
from pathlib import Path

from runtime_builder import build_runtime


def run() -> None:
    if not os.environ.get("DATABASE_URL", "").strip():
        raise AssertionError("DATABASE_URL is required")

    runtime = build_runtime(Path(tempfile.mkdtemp(prefix="jj-pg-analytics-v2-")) / "runtime")
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

        expected = [
            "jj_hand_actions",
            "jj_hand_history",
            "jj_hand_players",
            "jj_hand_reviews",
            "jj_hand_snapshots",
        ]
        with db.connect() as con:
            placeholders = ",".join("?" for _ in expected)
            rows = con.execute(
                f"SELECT table_name FROM information_schema.tables WHERE table_schema=? AND table_name IN ({placeholders})",
                ["public", *expected],
            ).fetchall()
            assert {str(row["table_name"]) for row in rows} == set(expected)

            suffix = uuid.uuid4().hex[:8]
            alice = db.insert_returning_id(
                con,
                "INSERT INTO users(name,email,password_hash,role,arena_chips,xp,approved,disabled,ranking_name,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                ("アリスPG", f"pg-alice-{suffix}@jj.invalid", "test-hash", "member", 0, 0, 1, 0, "アリスPG", db.utcnow()),
            )
            bob = db.insert_returning_id(
                con,
                "INSERT INTO users(name,email,password_hash,role,arena_chips,xp,approved,disabled,ranking_name,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                ("ボブPG", f"pg-bob-{suffix}@jj.invalid", "test-hash", "member", 0, 0, 1, 0, "ボブPG", db.utcnow()),
            )

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
                "SELECT completed_at,partial_capture,result_type FROM jj_hand_history WHERE hand_id=?",
                (hand_id,),
            ).fetchone()
            assert hand is not None and hand["completed_at"]
            assert int(hand["partial_capture"] or 0) == 0
            assert str(hand["result_type"]) == "uncontested"

            rows = con.execute(
                "SELECT user_id,position,starting_stack,ending_stack,net_chips,net_bb FROM jj_hand_players WHERE hand_id=? ORDER BY seat",
                (hand_id,),
            ).fetchall()
            by_uid = {int(row["user_id"]): dict(row) for row in rows}
            assert by_uid[alice]["position"] == "BTN/SB"
            assert float(by_uid[alice]["net_bb"]) == -0.5, by_uid[alice]
            # JJ Arena's existing online-table rule charges 10% rake even when
            # the hand ends preflop (5bb cap). A 1.5bb pot therefore returns
            # 1.35bb to the BB winner: +0.35bb net after posting 1bb.
            assert float(by_uid[bob]["net_bb"]) == 0.35, by_uid[bob]
            assert int(by_uid[alice]["net_chips"]) + int(by_uid[bob]["net_chips"]) == -15, by_uid

            actions = con.execute(
                "SELECT user_id,street,action FROM jj_hand_actions WHERE hand_id=? ORDER BY seq",
                (hand_id,),
            ).fetchall()
            assert len(actions) == 1
            assert int(actions[0]["user_id"]) == alice
            assert str(actions[0]["street"]) == "preflop"
            assert str(actions[0]["action"]) == "fold"

            snapshots = con.execute(
                "SELECT state_json FROM jj_hand_snapshots WHERE hand_id=? ORDER BY seq",
                (hand_id,),
            ).fetchall()
            assert snapshots
            assert all('"deck"' not in str(row["state_json"]) for row in snapshots)

        alice_summary = hand_analytics._summary_payload(alice, "all", None)
        bob_summary = hand_analytics._summary_payload(bob, "all", None)
        assert alice_summary["overall"]["hands"] >= 1
        assert bob_summary["overall"]["hands"] >= 1
        assert float(alice_summary["overall"]["net_bb"]) <= -0.5
        assert float(bob_summary["overall"]["net_bb"]) >= 0.35

        detail = hand_analytics._detail_payload(hand_id, alice)
        private_cards = {int(player["user_id"]): player["cards"] for player in detail["players"]}
        assert len(private_cards[alice]) == 2
        assert private_cards[bob] == ["??", "??"]

        public = poker_engine.public_state(state, alice)
        public_cards = {int(player["user_id"]): list(player.get("cards") or []) for player in public["seats"]}
        assert len(public_cards[alice]) == 2
        assert public_cards[bob] == []

        print("JJ_HAND_ANALYTICS_POSTGRES_V2_OK")
    finally:
        if str(runtime) in sys.path:
            sys.path.remove(str(runtime))
        for name in ("db", "server", "poker_engine"):
            sys.modules.pop(name, None)
        sys.modules.update(old_modules)


if __name__ == "__main__":
    run()
