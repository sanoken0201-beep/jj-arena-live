from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

from runtime_builder import build_runtime


def run() -> None:
    work = Path(tempfile.mkdtemp(prefix="jj-stat-definitions-"))
    runtime = build_runtime(work / "runtime")
    old_env = {k: os.environ.get(k) for k in ("DATABASE_URL", "JJ_DB_PATH", "JJ_ADMIN_NAME", "JJ_ADMIN_PIN", "JJ_ENABLE_DEMO_MEMBER")}
    os.environ.pop("DATABASE_URL", None)
    os.environ["JJ_DB_PATH"] = str(work / "stats.sqlite3")
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
        import server  # type: ignore
        import hand_analytics
        import hand_analytics_hardening

        hand_analytics.install(server.app, server, db)
        hand_analytics_hardening.install(hand_analytics, server)

        with db.connect() as con:
            users = {}
            for name in ("アリス", "ボブ", "キャロル", "デイブ"):
                uid = db.insert_returning_id(
                    con,
                    "INSERT INTO users(name,email,password_hash,role,arena_chips,xp,approved,disabled,ranking_name,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (name, f"stat-{name}@jj.invalid", db.hash_password("123456"), "member", 0, 0, 1, 0, name, db.utcnow()),
                )
                users[name] = uid

        def seed(hand_id: str, positions: list[tuple[str, str]], actions: list[dict], board=None):
            board = list(board or [])
            with db.connect() as con:
                con.execute(
                    """INSERT INTO jj_hand_history(
                         hand_id,table_id,table_name,hand_no,started_at,completed_at,small_blind,big_blind,
                         button_seat,small_blind_seat,big_blind_seat,player_count,board_json,reached_street,
                         result_type,showdown,partial_capture,summary_json
                       ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        hand_id, "jj-table-a", "JJ Table A", 1, db.utcnow(), db.utcnow(), 50, 100,
                        0, 1, 2, len(positions), json.dumps(board), "flop" if board else "preflop",
                        "test", 0, 0, "{}",
                    ),
                )
                for seat, (name, position) in enumerate(positions):
                    con.execute(
                        """INSERT INTO jj_hand_players(
                             hand_id,user_id,player_name,seat,position,hole_cards_json,starting_stack,
                             starting_stack_bb,effective_stack,effective_stack_bb,ending_stack,net_chips,net_bb
                           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (hand_id, users[name], name, seat, position, "[]", 15000, 150, 15000, 150, 15000, 0, 0),
                    )
                for seq, action in enumerate(actions, 1):
                    name = action["name"]
                    con.execute(
                        """INSERT INTO jj_hand_actions(
                             hand_id,seq,user_id,player_name,street,action,amount_chips,amount_bb,to_chips,to_bb,
                             pot_before,facing_chips,is_aggressive,raise_number,decision_seconds,timed_out,created_at
                           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            hand_id, seq, users[name], name, action.get("street", "preflop"), action["action"],
                            action.get("amount", 0), action.get("amount", 0) / 100,
                            action.get("to"), (action.get("to") / 100 if action.get("to") is not None else None),
                            action.get("pot", 0), action.get("facing", 0), action.get("aggressive", 0),
                            action.get("raise_number", 0), 1.0, 0, db.utcnow(),
                        ),
                    )
            state = {"hand": {"board": board, "showdown": None}, "last_result": {"winners": []}}
            with db.connect() as con:
                return hand_analytics._compute_flags(con, hand_id, state)

        # Caller between the opener and squeezer must not hide the squeezer's
        # genuine 3bet opportunity from the denominator.
        flags = seed(
            "threebet-squeeze",
            [("アリス", "UTG"), ("ボブ", "HJ"), ("キャロル", "CO"), ("デイブ", "BB")],
            [
                {"name": "アリス", "action": "raise", "amount": 300, "to": 300, "aggressive": 1, "raise_number": 1},
                {"name": "ボブ", "action": "call", "amount": 300},
                {"name": "キャロル", "action": "raise", "amount": 1200, "to": 1200, "aggressive": 1, "raise_number": 2},
                {"name": "アリス", "action": "fold"},
            ],
        )
        assert flags[users["ボブ"]]["three_bet_opp"] == 1
        assert flags[users["キャロル"]]["three_bet_opp"] == 1
        assert flags[users["キャロル"]]["three_bet"] == 1
        assert flags[users["アリス"]]["faced_three_bet"] == 1
        assert flags[users["アリス"]]["folded_to_three_bet"] == 1

        # If a cold 4bet happens before the opener acts again, the opener's fold
        # is no longer classified as a direct fold-to-3bet event.
        flags = seed(
            "cold-fourbet",
            [("アリス", "UTG"), ("ボブ", "HJ"), ("キャロル", "CO"), ("デイブ", "BTN")],
            [
                {"name": "アリス", "action": "raise", "amount": 300, "to": 300, "aggressive": 1, "raise_number": 1},
                {"name": "ボブ", "action": "raise", "amount": 900, "to": 900, "aggressive": 1, "raise_number": 2},
                {"name": "キャロル", "action": "raise", "amount": 2400, "to": 2400, "aggressive": 1, "raise_number": 3},
                {"name": "アリス", "action": "fold"},
            ],
        )
        assert flags[users["アリス"]]["faced_three_bet"] == 1
        assert flags[users["アリス"]]["folded_to_three_bet"] == 0

        # BTN open followed by an SB 3bet means the BB's later fold is not a
        # direct BB-vs-steal response.
        flags = seed(
            "steal-intervening-threebet",
            [("アリス", "BTN"), ("ボブ", "SB"), ("キャロル", "BB")],
            [
                {"name": "アリス", "action": "raise", "amount": 250, "to": 250, "aggressive": 1, "raise_number": 1},
                {"name": "ボブ", "action": "raise", "amount": 900, "to": 900, "aggressive": 1, "raise_number": 2},
                {"name": "キャロル", "action": "fold"},
            ],
        )
        assert flags[users["アリス"]]["steal_attempt"] == 1
        assert flags[users["キャロル"]]["bb_vs_steal"] == 0
        assert flags[users["キャロル"]]["folded_bb_to_steal"] == 0

        # A player who acts only after another opponent raises the cbet is not
        # recorded as directly facing the original cbet.
        flags = seed(
            "multiway-cbet-raise",
            [("アリス", "BTN"), ("ボブ", "SB"), ("キャロル", "BB")],
            [
                {"name": "アリス", "action": "raise", "amount": 300, "to": 300, "aggressive": 1, "raise_number": 1},
                {"name": "ボブ", "action": "call", "amount": 250},
                {"name": "キャロル", "action": "call", "amount": 200},
                {"name": "ボブ", "street": "flop", "action": "check"},
                {"name": "キャロル", "street": "flop", "action": "check"},
                {"name": "アリス", "street": "flop", "action": "raise", "amount": 500, "to": 500, "aggressive": 1},
                {"name": "ボブ", "street": "flop", "action": "raise", "amount": 1500, "to": 1500, "aggressive": 1},
                {"name": "キャロル", "street": "flop", "action": "fold"},
            ],
            board=["2c", "8d", "Jh"],
        )
        assert flags[users["アリス"]]["cbet_opp"] == 1
        assert flags[users["アリス"]]["cbet"] == 1
        assert flags[users["ボブ"]]["faced_cbet"] == 1
        assert flags[users["ボブ"]]["folded_to_cbet"] == 0
        assert flags[users["キャロル"]]["faced_cbet"] == 0
        assert flags[users["キャロル"]]["folded_to_cbet"] == 0

        print("JJ_STAT_DEFINITIONS_SMOKE_OK")
    finally:
        if str(runtime) in sys.path:
            sys.path.remove(str(runtime))
        for name in ("db", "server", "poker_engine"):
            sys.modules.pop(name, None)
        sys.modules.update(old_modules)
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


if __name__ == "__main__":
    run()
