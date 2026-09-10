from __future__ import annotations

import json
import math
import re
import threading
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

_DB = None
_SERVER = None
_LOCK = threading.RLock()
_ORIGINAL_SAVE_TABLE = None
_ORIGINAL_APPLY_ACTION = None
DEFAULT_DECISION_SECONDS = 45.0
SESSION_GAP_MINUTES = 30


class HandReviewIn(BaseModel):
    bookmarked: bool = False
    note: str = Field(default="", max_length=4000)
    tags: list[str] = Field(default_factory=list, max_length=12)


def _now() -> str:
    if _DB is not None:
        try:
            return _DB.utcnow()
        except Exception:
            pass
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _loads(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
        return out if math.isfinite(out) else default
    except Exception:
        return default


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _ensure_schema() -> None:
    uid = "BIGINT" if getattr(_DB, "IS_POSTGRES", False) else "INTEGER"
    with _DB.connect() as con:
        con.executescript(
            f"""
            CREATE TABLE IF NOT EXISTS jj_hand_history(
              hand_id TEXT PRIMARY KEY,
              table_id TEXT NOT NULL,
              table_name TEXT NOT NULL,
              hand_no INTEGER NOT NULL,
              started_at TEXT NOT NULL,
              completed_at TEXT,
              small_blind INTEGER NOT NULL,
              big_blind INTEGER NOT NULL,
              button_seat INTEGER NOT NULL,
              small_blind_seat INTEGER,
              big_blind_seat INTEGER,
              player_count INTEGER NOT NULL,
              board_json TEXT NOT NULL DEFAULT '[]',
              reached_street TEXT NOT NULL DEFAULT 'preflop',
              result_type TEXT,
              showdown INTEGER NOT NULL DEFAULT 0,
              partial_capture INTEGER NOT NULL DEFAULT 0,
              summary_json TEXT NOT NULL DEFAULT '{{}}'
            );
            CREATE INDEX IF NOT EXISTS idx_jj_hand_history_completed
              ON jj_hand_history(completed_at);
            CREATE INDEX IF NOT EXISTS idx_jj_hand_history_table
              ON jj_hand_history(table_id,completed_at);

            CREATE TABLE IF NOT EXISTS jj_hand_players(
              hand_id TEXT NOT NULL REFERENCES jj_hand_history(hand_id) ON DELETE CASCADE,
              user_id {uid} NOT NULL REFERENCES users(id),
              player_name TEXT NOT NULL,
              seat INTEGER NOT NULL,
              position TEXT NOT NULL,
              hole_cards_json TEXT NOT NULL DEFAULT '[]',
              starting_stack INTEGER NOT NULL DEFAULT 0,
              starting_stack_bb REAL NOT NULL DEFAULT 0,
              effective_stack INTEGER NOT NULL DEFAULT 0,
              effective_stack_bb REAL NOT NULL DEFAULT 0,
              ending_stack INTEGER,
              net_chips INTEGER,
              net_bb REAL,
              vpip INTEGER NOT NULL DEFAULT 0,
              pfr INTEGER NOT NULL DEFAULT 0,
              three_bet_opp INTEGER NOT NULL DEFAULT 0,
              three_bet INTEGER NOT NULL DEFAULT 0,
              faced_three_bet INTEGER NOT NULL DEFAULT 0,
              folded_to_three_bet INTEGER NOT NULL DEFAULT 0,
              steal_opp INTEGER NOT NULL DEFAULT 0,
              steal_attempt INTEGER NOT NULL DEFAULT 0,
              bb_vs_steal INTEGER NOT NULL DEFAULT 0,
              folded_bb_to_steal INTEGER NOT NULL DEFAULT 0,
              saw_flop INTEGER NOT NULL DEFAULT 0,
              cbet_opp INTEGER NOT NULL DEFAULT 0,
              cbet INTEGER NOT NULL DEFAULT 0,
              faced_cbet INTEGER NOT NULL DEFAULT 0,
              folded_to_cbet INTEGER NOT NULL DEFAULT 0,
              went_showdown INTEGER NOT NULL DEFAULT 0,
              won_showdown INTEGER NOT NULL DEFAULT 0,
              won_hand INTEGER NOT NULL DEFAULT 0,
              aggressive_actions INTEGER NOT NULL DEFAULT 0,
              call_actions INTEGER NOT NULL DEFAULT 0,
              check_actions INTEGER NOT NULL DEFAULT 0,
              decision_count INTEGER NOT NULL DEFAULT 0,
              decision_seconds REAL NOT NULL DEFAULT 0,
              timeout_count INTEGER NOT NULL DEFAULT 0,
              PRIMARY KEY(hand_id,user_id)
            );
            CREATE INDEX IF NOT EXISTS idx_jj_hand_players_user
              ON jj_hand_players(user_id,hand_id);
            CREATE INDEX IF NOT EXISTS idx_jj_hand_players_position
              ON jj_hand_players(user_id,position);

            CREATE TABLE IF NOT EXISTS jj_hand_actions(
              hand_id TEXT NOT NULL REFERENCES jj_hand_history(hand_id) ON DELETE CASCADE,
              seq INTEGER NOT NULL,
              user_id {uid} NOT NULL REFERENCES users(id),
              player_name TEXT NOT NULL,
              street TEXT NOT NULL,
              action TEXT NOT NULL,
              amount_chips INTEGER NOT NULL DEFAULT 0,
              amount_bb REAL NOT NULL DEFAULT 0,
              to_chips INTEGER,
              to_bb REAL,
              pot_before INTEGER NOT NULL DEFAULT 0,
              facing_chips INTEGER NOT NULL DEFAULT 0,
              is_aggressive INTEGER NOT NULL DEFAULT 0,
              raise_number INTEGER NOT NULL DEFAULT 0,
              decision_seconds REAL,
              timed_out INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL,
              PRIMARY KEY(hand_id,seq)
            );
            CREATE INDEX IF NOT EXISTS idx_jj_hand_actions_user
              ON jj_hand_actions(user_id,hand_id);

            CREATE TABLE IF NOT EXISTS jj_hand_snapshots(
              hand_id TEXT NOT NULL REFERENCES jj_hand_history(hand_id) ON DELETE CASCADE,
              seq INTEGER NOT NULL,
              street TEXT NOT NULL,
              state_json TEXT NOT NULL,
              created_at TEXT NOT NULL,
              PRIMARY KEY(hand_id,seq)
            );

            CREATE TABLE IF NOT EXISTS jj_hand_reviews(
              hand_id TEXT NOT NULL REFERENCES jj_hand_history(hand_id) ON DELETE CASCADE,
              user_id {uid} NOT NULL REFERENCES users(id),
              bookmarked INTEGER NOT NULL DEFAULT 0,
              note TEXT NOT NULL DEFAULT '',
              tags_json TEXT NOT NULL DEFAULT '[]',
              updated_at TEXT NOT NULL,
              PRIMARY KEY(hand_id,user_id)
            );
            """
        )


def _position_map(state: dict[str, Any]) -> dict[int, str]:
    seats = [
        p for p in state.get("seats", [])
        if len(p.get("cards") or []) == 2 or p.get("in_hand")
    ]
    if not seats:
        return {}
    max_seats = max(2, _as_int(state.get("max_seats"), 6))
    button = _as_int(state.get("button_seat"), -1)
    seats = sorted(seats, key=lambda p: ((_as_int(p.get("seat")) - button) % max_seats))
    labels = {
        2: ["BTN/SB", "BB"],
        3: ["BTN", "SB", "BB"],
        4: ["BTN", "SB", "BB", "CO"],
        5: ["BTN", "SB", "BB", "UTG", "CO"],
        6: ["BTN", "SB", "BB", "UTG", "HJ", "CO"],
        7: ["BTN", "SB", "BB", "UTG", "UTG+1", "HJ", "CO"],
        8: ["BTN", "SB", "BB", "UTG", "UTG+1", "MP", "HJ", "CO"],
        9: ["BTN", "SB", "BB", "UTG", "UTG+1", "MP", "LJ", "HJ", "CO"],
    }.get(len(seats))
    if labels is None:
        labels = [f"P{i+1}" for i in range(len(seats))]
        labels[0] = "BTN"
    return {_as_int(p.get("user_id")): labels[i] for i, p in enumerate(seats)}


def _starting_stack(player: dict[str, Any], phase: str) -> int:
    if phase != "complete":
        return max(0, _as_int(player.get("stack")) + _as_int(player.get("contributed")))
    return max(0, _as_int(player.get("stack")))


def _sanitize_state(state: dict[str, Any]) -> dict[str, Any]:
    hand = state.get("hand") or {}
    return {
        "table_id": str(state.get("id") or ""),
        "table_name": str(state.get("name") or ""),
        "status": str(state.get("status") or ""),
        "small_blind": _as_int(state.get("small_blind")),
        "big_blind": _as_int(state.get("big_blind")),
        "button_seat": _as_int(state.get("button_seat"), -1),
        "hand": {
            "id": str(hand.get("id") or ""),
            "phase": str(hand.get("phase") or ""),
            "board": list(hand.get("board") or []),
            "current_bet": _as_int(hand.get("current_bet")),
            "min_raise": _as_int(hand.get("min_raise")),
            "action_seat": hand.get("action_seat"),
            "small_blind_seat": hand.get("small_blind_seat"),
            "big_blind_seat": hand.get("big_blind_seat"),
        },
        "seats": [
            {
                "user_id": _as_int(p.get("user_id")),
                "name": str(p.get("name") or ""),
                "seat": _as_int(p.get("seat")),
                "stack": _as_int(p.get("stack")),
                "round_bet": _as_int(p.get("round_bet")),
                "contributed": _as_int(p.get("contributed")),
                "in_hand": bool(p.get("in_hand")),
                "folded": bool(p.get("folded")),
                "all_in": bool(p.get("all_in")),
            }
            for p in state.get("seats", [])
        ],
    }


def _next_snapshot_seq(con, hand_id: str) -> int:
    row = con.execute(
        "SELECT COALESCE(MAX(seq),-1)+1 n FROM jj_hand_snapshots WHERE hand_id=?",
        (hand_id,),
    ).fetchone()
    return _as_int(row["n"] if row else 0)


def _store_snapshot(con, state: dict[str, Any], hand_id: str) -> None:
    sanitized = _sanitize_state(state)
    encoded = _json(sanitized)
    last = con.execute(
        "SELECT state_json FROM jj_hand_snapshots WHERE hand_id=? ORDER BY seq DESC LIMIT 1",
        (hand_id,),
    ).fetchone()
    if last and str(last["state_json"]) == encoded:
        return
    con.execute(
        "INSERT INTO jj_hand_snapshots(hand_id,seq,street,state_json,created_at) VALUES (?,?,?,?,?)",
        (
            hand_id,
            _next_snapshot_seq(con, hand_id),
            str((state.get("hand") or {}).get("phase") or "unknown"),
            encoded,
            _now(),
        ),
    )


def _ensure_hand(con, state: dict[str, Any]) -> str | None:
    hand = state.get("hand") or {}
    hand_id = str(hand.get("id") or "")
    if not hand_id:
        return None
    existing = con.execute(
        "SELECT hand_id FROM jj_hand_history WHERE hand_id=?",
        (hand_id,),
    ).fetchone()
    if existing:
        return hand_id

    # Do not resurrect an already-completed hand that predates analytics install.
    if str(hand.get("phase") or "") == "complete":
        return None

    log = list(hand.get("log") or [])
    partial = 1 if (str(hand.get("phase") or "") != "preflop" or len(log) > 1) else 0
    positions = _position_map(state)
    participants = [
        p for p in state.get("seats", [])
        if len(p.get("cards") or []) == 2 or p.get("in_hand")
    ]
    bb = max(1, _as_int(state.get("big_blind"), 1))
    stacks = {_as_int(p.get("user_id")): _starting_stack(p, str(hand.get("phase") or "")) for p in participants}

    con.execute(
        """INSERT INTO jj_hand_history(
             hand_id,table_id,table_name,hand_no,started_at,completed_at,
             small_blind,big_blind,button_seat,small_blind_seat,big_blind_seat,
             player_count,board_json,reached_street,result_type,showdown,partial_capture,summary_json
           ) VALUES (?,?,?,?,?,NULL,?,?,?,?,?,?,'[]','preflop',NULL,0,?,'{}')""",
        (
            hand_id,
            str(state.get("id") or ""),
            str(state.get("name") or ""),
            _as_int(state.get("hand_no")),
            _now(),
            _as_int(state.get("small_blind")),
            bb,
            _as_int(state.get("button_seat"), -1),
            hand.get("small_blind_seat"),
            hand.get("big_blind_seat"),
            len(participants),
            partial,
        ),
    )
    for p in participants:
        uid = _as_int(p.get("user_id"))
        start = stacks.get(uid, 0)
        other_stacks = [v for k, v in stacks.items() if k != uid]
        effective = min(start, max(other_stacks)) if other_stacks else start
        con.execute(
            """INSERT INTO jj_hand_players(
                 hand_id,user_id,player_name,seat,position,hole_cards_json,
                 starting_stack,starting_stack_bb,effective_stack,effective_stack_bb
               ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                hand_id,
                uid,
                str(p.get("name") or ""),
                _as_int(p.get("seat")),
                positions.get(uid, "—"),
                _json(list(p.get("cards") or [])),
                start,
                round(start / bb, 3),
                effective,
                round(effective / bb, 3),
            ),
        )
    return hand_id


def _winner_ids(result: dict[str, Any]) -> set[int]:
    return {
        _as_int(w.get("user_id"))
        for w in (result.get("winners") or [])
        if _as_int(w.get("user_id")) > 0
    }


def _compute_flags(con, hand_id: str, state: dict[str, Any]) -> dict[int, dict[str, Any]]:
    player_rows = con.execute(
        "SELECT * FROM jj_hand_players WHERE hand_id=? ORDER BY seat",
        (hand_id,),
    ).fetchall()
    players = {int(r["user_id"]): dict(r) for r in player_rows}
    flags: dict[int, dict[str, Any]] = {
        uid: {
            "vpip": 0, "pfr": 0, "three_bet_opp": 0, "three_bet": 0,
            "faced_three_bet": 0, "folded_to_three_bet": 0, "steal_opp": 0, "steal_attempt": 0,
            "bb_vs_steal": 0, "folded_bb_to_steal": 0, "saw_flop": 0,
            "cbet_opp": 0, "cbet": 0, "faced_cbet": 0, "folded_to_cbet": 0,
            "went_showdown": 0, "won_showdown": 0, "won_hand": 0,
            "aggressive_actions": 0, "call_actions": 0, "check_actions": 0,
            "decision_count": 0, "decision_seconds": 0.0, "timeout_count": 0,
        }
        for uid in players
    }
    actions = [
        dict(r) for r in con.execute(
            "SELECT * FROM jj_hand_actions WHERE hand_id=? ORDER BY seq",
            (hand_id,),
        ).fetchall()
    ]
    by_street: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for a in actions:
        by_street[str(a["street"])].append(a)
        uid = int(a["user_id"])
        if uid not in flags:
            continue
        if int(a["is_aggressive"] or 0):
            flags[uid]["aggressive_actions"] += 1
        elif str(a["action"]) in {"call", "allin_call"}:
            flags[uid]["call_actions"] += 1
        elif str(a["action"]) == "check":
            flags[uid]["check_actions"] += 1
        if a["decision_seconds"] is not None:
            flags[uid]["decision_count"] += 1
            flags[uid]["decision_seconds"] += _as_float(a["decision_seconds"])
        flags[uid]["timeout_count"] += int(a["timed_out"] or 0)

    pre = by_street.get("preflop", [])
    pre_actions_by_user: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for a in pre:
        pre_actions_by_user[int(a["user_id"])].append(a)
    for uid in players:
        acts = pre_actions_by_user.get(uid, [])
        flags[uid]["vpip"] = int(any(
            str(a["action"]) in {"call", "raise", "allin_raise", "allin_call"}
            and (_as_int(a["amount_chips"]) > 0)
            for a in acts
        ))
        flags[uid]["pfr"] = int(any(int(a["is_aggressive"] or 0) for a in acts))

    # Preflop raise order drives 3-bet and steal opportunities.
    # A steal opportunity exists when action reaches CO/BTN/SB unopened.
    voluntary_raise_seen = False
    for a in pre:
        uid = int(a["user_id"])
        if not voluntary_raise_seen and str(players.get(uid, {}).get("position") or "") in {"CO", "BTN", "BTN/SB", "SB"}:
            flags[uid]["steal_opp"] = 1
        if int(a["is_aggressive"] or 0):
            voluntary_raise_seen = True

    first_aggressor = None
    three_bettor = None
    opener = None
    for a in pre:
        uid = int(a["user_id"])
        if int(a["is_aggressive"] or 0):
            rn = int(a["raise_number"] or 0)
            if rn == 1:
                first_aggressor = uid
                opener = uid
                pos = str(players.get(uid, {}).get("position") or "")
                if pos in {"CO", "BTN", "BTN/SB", "SB"}:
                    flags[uid]["steal_attempt"] = 1
            elif rn == 2:
                three_bettor = uid
                flags[uid]["three_bet"] = 1
                if opener in flags:
                    flags[opener]["faced_three_bet"] = 1

    # A decision against an existing opener is a 3-bet opportunity.
    if first_aggressor is not None:
        open_idx = next((i for i, a in enumerate(pre) if int(a["is_aggressive"] or 0) and int(a["raise_number"] or 0) == 1), None)
        if open_idx is not None:
            seen = set()
            for a in pre[open_idx + 1:]:
                uid = int(a["user_id"])
                if uid == first_aggressor or uid in seen:
                    continue
                seen.add(uid)
                flags[uid]["three_bet_opp"] = 1
                if int(a["is_aggressive"] or 0) and int(a["raise_number"] or 0) == 2:
                    flags[uid]["three_bet"] = 1
                if three_bettor is not None:
                    break

    if opener is not None and flags.get(opener, {}).get("faced_three_bet"):
        later = [
            a for a in pre
            if int(a["user_id"]) == opener and int(a["seq"]) >
            min(int(x["seq"]) for x in pre if int(x["user_id"]) == three_bettor and int(x["raise_number"] or 0) == 2)
        ] if three_bettor is not None else []
        if later and str(later[0]["action"]) == "fold":
            flags[opener]["folded_to_three_bet"] = 1

    # BB response to a late-position first raise.
    if opener is not None and flags.get(opener, {}).get("steal_attempt"):
        bb_uid = next((uid for uid, p in players.items() if str(p.get("position")) == "BB"), None)
        if bb_uid is not None and bb_uid != opener:
            steal_seq = next(
                (int(a["seq"]) for a in pre if int(a["user_id"]) == opener and int(a["raise_number"] or 0) == 1),
                None,
            )
            response = next(
                (a for a in pre if int(a["user_id"]) == bb_uid and (steal_seq is None or int(a["seq"]) > steal_seq)),
                None,
            )
            if response:
                flags[bb_uid]["bb_vs_steal"] = 1
                flags[bb_uid]["folded_bb_to_steal"] = int(str(response["action"]) == "fold")

    board = list((state.get("hand") or {}).get("board") or [])
    if len(board) >= 3:
        for uid in players:
            folded_pre = any(str(a["action"]) == "fold" for a in pre_actions_by_user.get(uid, []))
            flags[uid]["saw_flop"] = int(not folded_pre)

    # Continuation-bet opportunity: last preflop aggressor has a flop decision.
    pre_aggressors = [a for a in pre if int(a["is_aggressive"] or 0)]
    last_pre_aggressor = int(pre_aggressors[-1]["user_id"]) if pre_aggressors else None
    flop = by_street.get("flop", [])
    if last_pre_aggressor in flags and flags[last_pre_aggressor]["saw_flop"]:
        hero_flop = [a for a in flop if int(a["user_id"]) == last_pre_aggressor]
        if hero_flop:
            flags[last_pre_aggressor]["cbet_opp"] = 1
            first_hero = hero_flop[0]
            if int(first_hero["is_aggressive"] or 0):
                flags[last_pre_aggressor]["cbet"] = 1
                cbet_seq = int(first_hero["seq"])
                for uid in players:
                    if uid == last_pre_aggressor or not flags[uid]["saw_flop"]:
                        continue
                    response = next(
                        (a for a in flop if int(a["user_id"]) == uid and int(a["seq"]) > cbet_seq),
                        None,
                    )
                    if response:
                        flags[uid]["faced_cbet"] = 1
                        flags[uid]["folded_to_cbet"] = int(str(response["action"]) == "fold")

    showdown_scores = ((state.get("hand") or {}).get("showdown") or {}).get("scores") or {}
    showdown_ids = {_as_int(k) for k in showdown_scores.keys()}
    winners = _winner_ids(state.get("last_result") or {})
    for uid in players:
        flags[uid]["went_showdown"] = int(uid in showdown_ids)
        flags[uid]["won_hand"] = int(uid in winners)
        flags[uid]["won_showdown"] = int(uid in showdown_ids and uid in winners)
    return flags


def _finalize_hand(con, state: dict[str, Any], hand_id: str) -> None:
    row = con.execute(
        "SELECT completed_at,big_blind FROM jj_hand_history WHERE hand_id=?",
        (hand_id,),
    ).fetchone()
    if not row or row["completed_at"]:
        return
    hand = state.get("hand") or {}
    if str(hand.get("phase") or "") != "complete":
        return

    result = state.get("last_result") or {}
    board = list(hand.get("board") or result.get("board") or [])
    showdown = bool((hand.get("showdown") or {}).get("scores"))
    bb = max(1, _as_int(row["big_blind"], 1))
    seat_by_user = {_as_int(p.get("user_id")): p for p in state.get("seats", [])}
    flags = _compute_flags(con, hand_id, state)

    for uid, f in flags.items():
        p = seat_by_user.get(uid)
        existing = con.execute(
            "SELECT starting_stack FROM jj_hand_players WHERE hand_id=? AND user_id=?",
            (hand_id, uid),
        ).fetchone()
        start = _as_int(existing["starting_stack"] if existing else 0)
        ending = _as_int(p.get("stack")) if p is not None else start
        net = ending - start
        con.execute(
            """UPDATE jj_hand_players SET
               ending_stack=?,net_chips=?,net_bb=?,
               vpip=?,pfr=?,three_bet_opp=?,three_bet=?,faced_three_bet=?,folded_to_three_bet=?,
               steal_opp=?,steal_attempt=?,bb_vs_steal=?,folded_bb_to_steal=?,saw_flop=?,
               cbet_opp=?,cbet=?,faced_cbet=?,folded_to_cbet=?,
               went_showdown=?,won_showdown=?,won_hand=?,
               aggressive_actions=?,call_actions=?,check_actions=?,
               decision_count=?,decision_seconds=?,timeout_count=?
               WHERE hand_id=? AND user_id=?""",
            (
                ending, net, round(net / bb, 4),
                f["vpip"], f["pfr"], f["three_bet_opp"], f["three_bet"],
                f["faced_three_bet"], f["folded_to_three_bet"],
                f["steal_opp"], f["steal_attempt"], f["bb_vs_steal"], f["folded_bb_to_steal"],
                f["saw_flop"], f["cbet_opp"], f["cbet"], f["faced_cbet"],
                f["folded_to_cbet"], f["went_showdown"], f["won_showdown"],
                f["won_hand"], f["aggressive_actions"], f["call_actions"],
                f["check_actions"], f["decision_count"], round(f["decision_seconds"], 3),
                f["timeout_count"], hand_id, uid,
            ),
        )

    pot_total = sum(_as_int(w.get("amount")) for w in (result.get("winners") or []))
    summary = {
        "message": str(result.get("message") or ""),
        "winners": [
            {
                "user_id": _as_int(w.get("user_id")),
                "name": str(w.get("name") or ""),
                "amount": _as_int(w.get("amount")),
                "hand": str(w.get("hand") or ""),
            }
            for w in (result.get("winners") or [])
        ],
        "pot_awarded": pot_total,
    }
    reached = "river" if len(board) >= 5 else "turn" if len(board) >= 4 else "flop" if len(board) >= 3 else "preflop"
    con.execute(
        """UPDATE jj_hand_history SET completed_at=?,board_json=?,reached_street=?,result_type=?,
           showdown=?,summary_json=? WHERE hand_id=?""",
        (_now(), _json(board), reached, str(result.get("type") or "complete"), 1 if showdown else 0, _json(summary), hand_id),
    )


def _observe_state(state: dict[str, Any]) -> None:
    hand = state.get("hand") or {}
    if not hand.get("id"):
        return
    with _LOCK:
        with _DB.connect() as con:
            hand_id = _ensure_hand(con, state)
            if not hand_id:
                return
            _store_snapshot(con, state, hand_id)
            _finalize_hand(con, state, hand_id)


def _decision_time(deadline: Any) -> tuple[float | None, int]:
    end = _parse_dt(str(deadline)) if deadline else None
    if end is None:
        return None, 0
    now = datetime.now(timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    remaining = (end - now).total_seconds()
    elapsed = max(0.0, min(DEFAULT_DECISION_SECONDS, DEFAULT_DECISION_SECONDS - remaining))
    return round(elapsed, 3), int(remaining <= 0)


def _record_action(context: dict[str, Any]) -> None:
    hand_id = context["hand_id"]
    with _LOCK:
        with _DB.connect() as con:
            if not con.execute(
                "SELECT 1 FROM jj_hand_history WHERE hand_id=?",
                (hand_id,),
            ).fetchone():
                # Mid-deploy action: create the partial hand before recording it.
                _ensure_hand(con, context["state_before"])
            if not con.execute(
                "SELECT 1 FROM jj_hand_history WHERE hand_id=?",
                (hand_id,),
            ).fetchone():
                return
            row = con.execute(
                "SELECT COALESCE(MAX(seq),0)+1 n FROM jj_hand_actions WHERE hand_id=?",
                (hand_id,),
            ).fetchone()
            seq = _as_int(row["n"] if row else 1, 1)
            prev_aggr = con.execute(
                "SELECT COUNT(*) c FROM jj_hand_actions WHERE hand_id=? AND street='preflop' AND is_aggressive=1",
                (hand_id,),
            ).fetchone()
            aggressive = int(context["is_aggressive"])
            raise_number = (_as_int(prev_aggr["c"]) + 1) if aggressive and context["street"] == "preflop" else 0
            con.execute(
                """INSERT INTO jj_hand_actions(
                     hand_id,seq,user_id,player_name,street,action,amount_chips,amount_bb,
                     to_chips,to_bb,pot_before,facing_chips,is_aggressive,raise_number,
                     decision_seconds,timed_out,created_at
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    hand_id, seq, context["user_id"], context["player_name"],
                    context["street"], context["action"], context["amount_chips"],
                    context["amount_bb"], context["to_chips"], context["to_bb"],
                    context["pot_before"], context["facing_chips"], aggressive,
                    raise_number, context["decision_seconds"], context["timed_out"], _now(),
                ),
            )


def _wrap_runtime() -> None:
    global _ORIGINAL_SAVE_TABLE, _ORIGINAL_APPLY_ACTION
    if getattr(_SERVER, "_jj_hand_analytics_wrapped", False):
        return
    _SERVER._jj_hand_analytics_wrapped = True
    _ORIGINAL_SAVE_TABLE = _SERVER.save_table
    _ORIGINAL_APPLY_ACTION = _SERVER.apply_action

    def tracked_save_table(state: dict[str, Any]):
        result = _ORIGINAL_SAVE_TABLE(state)
        try:
            _observe_state(state)
        except Exception as exc:
            print(f"JJ_HAND_ANALYTICS_OBSERVE_ERROR {type(exc).__name__}")
        return result

    def tracked_apply_action(state: dict[str, Any], user_id: int, action: str, amount: int | None = None):
        hand = state.get("hand") or {}
        player = next(
            (p for p in state.get("seats", []) if _as_int(p.get("user_id")) == _as_int(user_id)),
            None,
        )
        context = None
        if hand.get("id") and player:
            bb = max(1, _as_int(state.get("big_blind"), 1))
            current_bet = _as_int(hand.get("current_bet"))
            round_bet = _as_int(player.get("round_bet"))
            stack = _as_int(player.get("stack"))
            call_amount = max(0, min(current_bet - round_bet, stack))
            raw_action = str(action or "").lower()
            target = None
            paid = 0
            aggressive = 0
            stored_action = raw_action
            if raw_action == "call":
                paid = call_amount
            elif raw_action == "allin":
                target = round_bet + stack
                paid = stack
                aggressive = int(target > current_bet)
                stored_action = "allin_raise" if aggressive else "allin_call"
            elif raw_action == "raise":
                target = _as_int(amount)
                paid = max(0, target - round_bet)
                aggressive = 1
            decision_seconds, timed_out = _decision_time(hand.get("action_deadline"))
            context = {
                "state_before": json.loads(json.dumps(state)),
                "hand_id": str(hand.get("id")),
                "user_id": _as_int(user_id),
                "player_name": str(player.get("name") or ""),
                "street": str(hand.get("phase") or "unknown"),
                "action": stored_action,
                "amount_chips": paid,
                "amount_bb": round(paid / bb, 4),
                "to_chips": target,
                "to_bb": round(target / bb, 4) if target is not None else None,
                "pot_before": sum(_as_int(p.get("contributed")) for p in state.get("seats", [])),
                "facing_chips": call_amount,
                "is_aggressive": aggressive,
                "decision_seconds": decision_seconds,
                "timed_out": timed_out,
            }
        result = _ORIGINAL_APPLY_ACTION(state, user_id, action, amount)
        if context is not None:
            try:
                _record_action(context)
            except Exception as exc:
                print(f"JJ_HAND_ANALYTICS_ACTION_ERROR {type(exc).__name__}")
        return result

    _SERVER.save_table = tracked_save_table
    _SERVER.apply_action = tracked_apply_action


def _range_start(range_name: str) -> str | None:
    now = datetime.now(timezone.utc)
    if range_name == "7d":
        return (now - timedelta(days=7)).isoformat()
    if range_name == "30d":
        return (now - timedelta(days=30)).isoformat()
    if range_name == "90d":
        return (now - timedelta(days=90)).isoformat()
    return None


def _completed_player_rows(user_id: int, range_name: str = "all", table_id: str | None = None) -> list[dict[str, Any]]:
    where = ["p.user_id=?", "h.completed_at IS NOT NULL", "COALESCE(h.partial_capture,0)=0"]
    params: list[Any] = [user_id]
    start = _range_start(range_name)
    if start:
        where.append("h.completed_at>=?")
        params.append(start)
    if table_id:
        where.append("h.table_id=?")
        params.append(table_id)
    with _DB.connect() as con:
        rows = con.execute(
            f"""SELECT p.*,h.completed_at,h.started_at,h.table_id,h.table_name,h.board_json,
                       h.player_count,h.result_type,h.showdown,h.hand_no,h.big_blind
                FROM jj_hand_players p JOIN jj_hand_history h ON h.hand_id=p.hand_id
                WHERE {' AND '.join(where)}
                ORDER BY h.completed_at ASC""",
            params,
        ).fetchall()
    return [dict(r) for r in rows]


def _rate(rows: list[dict[str, Any]], numerator: str, denominator: str | None = None) -> dict[str, Any]:
    if denominator:
        eligible = [r for r in rows if _as_int(r.get(denominator))]
        n = sum(_as_int(r.get(numerator)) for r in eligible)
        d = len(eligible)
    else:
        d = len(rows)
        n = sum(_as_int(r.get(numerator)) for r in rows)
    return {"value": round(n * 100 / d, 1) if d else None, "n": d, "hits": n}


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    hands = len(rows)
    net_bb = round(sum(_as_float(r.get("net_bb")) for r in rows), 2)
    agg_actions = sum(_as_int(r.get("aggressive_actions")) for r in rows)
    calls = sum(_as_int(r.get("call_actions")) for r in rows)
    checks = sum(_as_int(r.get("check_actions")) for r in rows)
    decisions = sum(_as_int(r.get("decision_count")) for r in rows)
    seconds = sum(_as_float(r.get("decision_seconds")) for r in rows)
    timeouts = sum(_as_int(r.get("timeout_count")) for r in rows)
    won = sum(_as_int(r.get("won_hand")) for r in rows)
    return {
        "hands": hands,
        "net_bb": net_bb,
        "bb_per_100": round(net_bb * 100 / hands, 2) if hands else None,
        "hands_won": won,
        "hand_win_rate": round(won * 100 / hands, 1) if hands else None,
        "vpip": _rate(rows, "vpip"),
        "pfr": _rate(rows, "pfr"),
        "three_bet": _rate(rows, "three_bet", "three_bet_opp"),
        "fold_to_three_bet": _rate(rows, "folded_to_three_bet", "faced_three_bet"),
        "steal": _rate(rows, "steal_attempt", "steal_opp"),
        "fold_bb_to_steal": _rate(rows, "folded_bb_to_steal", "bb_vs_steal"),
        "cbet": _rate(rows, "cbet", "cbet_opp"),
        "fold_to_cbet": _rate(rows, "folded_to_cbet", "faced_cbet"),
        "wtsd": _rate(rows, "went_showdown", "saw_flop"),
        "wsd": _rate(rows, "won_showdown", "went_showdown"),
        "aggression_factor": round(agg_actions / calls, 2) if calls else (float(agg_actions) if agg_actions else None),
        "aggression_frequency": round(agg_actions * 100 / (agg_actions + calls + checks), 1)
        if (agg_actions + calls + checks) else None,
        "avg_decision_seconds": round(seconds / decisions, 1) if decisions else None,
        "decision_sample": decisions,
        "timeouts": timeouts,
    }


def _group_dimension(rows: list[dict[str, Any]], key_fn) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(key_fn(row))].append(row)
    out = []
    for key, items in grouped.items():
        data = _aggregate(items)
        out.append({"key": key, **data})
    out.sort(key=lambda x: (-int(x["hands"]), x["key"]))
    return out


def _stack_band(row: dict[str, Any]) -> str:
    bb = _as_float(row.get("effective_stack_bb"))
    if bb < 40:
        return "<40bb"
    if bb < 80:
        return "40–79bb"
    if bb < 120:
        return "80–119bb"
    if bb < 180:
        return "120–179bb"
    return "180bb+"


def _leak_signals(rows: list[dict[str, Any]], overall: dict[str, Any], positions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    hands = len(rows)
    vpip = overall["vpip"]["value"]
    pfr = overall["pfr"]["value"]
    if hands >= 100 and vpip is not None and pfr is not None and vpip - pfr >= 12:
        signals.append({
            "severity": "watch",
            "title": "VPIPとPFRの差が大きめ",
            "detail": f"{hands}ハンドで VPIP {vpip}% / PFR {pfr}%。コール主体になっている局面をハンド履歴で確認する価値があります。",
            "metric": "VPIP-PFR gap",
        })
    f3 = overall["fold_to_three_bet"]
    if f3["n"] >= 20 and f3["value"] is not None and f3["value"] >= 75:
        signals.append({
            "severity": "watch",
            "title": "3betに対するフォールドが多い傾向",
            "detail": f"3betを受けた {f3['n']} 回のうち {f3['value']}% でフォールド。ポジション別に防衛レンジを見直す候補です。",
            "metric": "Fold to 3bet",
        })
    three = overall["three_bet"]
    if three["n"] >= 40 and three["value"] is not None and three["value"] <= 4:
        signals.append({
            "severity": "watch",
            "title": "3bet頻度が低い傾向",
            "detail": f"3bet機会 {three['n']} 回で {three['value']}%。コールへ寄りすぎていないか確認してください。",
            "metric": "3bet",
        })
    cbet = overall["cbet"]
    if cbet["n"] >= 20 and cbet["value"] is not None and (cbet["value"] <= 35 or cbet["value"] >= 90):
        signals.append({
            "severity": "info",
            "title": "フロップCbet頻度が極端",
            "detail": f"Cbet機会 {cbet['n']} 回で {cbet['value']}%。ボードタイプ別に分けて確認すると原因を特定しやすくなります。",
            "metric": "Cbet",
        })
    pos = {p["key"]: p for p in positions}
    early = next((pos[k] for k in ("UTG", "HJ") if k in pos and pos[k]["hands"] >= 30), None)
    late = next((pos[k] for k in ("BTN", "CO", "BTN/SB") if k in pos and pos[k]["hands"] >= 30), None)
    if early and late:
        e = early["vpip"]["value"]
        l = late["vpip"]["value"]
        if e is not None and l is not None and e >= l + 8:
            signals.append({
                "severity": "watch",
                "title": "ポジションによる参加頻度が逆転",
                "detail": f"{early['key']} VPIP {e}% に対し {late['key']} {l}%。後ろのポジションで十分に広がっているか確認してください。",
                "metric": "Position VPIP",
            })
    if overall["timeouts"] >= 3:
        signals.append({
            "severity": "info",
            "title": "タイムアウトが複数回あります",
            "detail": f"対象期間に {overall['timeouts']} 回。難しい局面なのか、接続・操作上の問題なのかを履歴から切り分けられます。",
            "metric": "Timeout",
        })
    if not signals:
        signals.append({
            "severity": "ok",
            "title": "大きな頻度偏りはまだ検出されていません",
            "detail": "これはGTO判定ではありません。サンプルが増えるほど、ポジション・3bet・Cbet等の傾向検出が安定します。",
            "metric": "Sample",
        })
    return signals[:6]


def _trend(rows: list[dict[str, Any]], max_points: int = 300) -> list[dict[str, Any]]:
    total = 0.0
    points = []
    for row in rows:
        total += _as_float(row.get("net_bb"))
        points.append({
            "hand_id": row["hand_id"],
            "at": row.get("completed_at"),
            "net_bb": round(_as_float(row.get("net_bb")), 2),
            "cumulative_bb": round(total, 2),
        })
    if len(points) <= max_points:
        return points
    stride = math.ceil(len(points) / max_points)
    reduced = [points[i] for i in range(0, len(points), stride)]
    if reduced[-1] is not points[-1]:
        reduced.append(points[-1])
    return reduced


def _sessions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []
    sessions: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    prev = None
    for row in rows:
        at = _parse_dt(row.get("completed_at"))
        if current and prev and at and (at - prev) > timedelta(minutes=SESSION_GAP_MINUTES):
            sessions.append(current)
            current = []
        current.append(row)
        if at:
            prev = at
    if current:
        sessions.append(current)
    out = []
    for i, items in enumerate(reversed(sessions), 1):
        data = _aggregate(items)
        out.append({
            "id": f"session-{len(sessions)-i+1}",
            "started_at": items[0].get("started_at") or items[0].get("completed_at"),
            "ended_at": items[-1].get("completed_at"),
            "tables": sorted({str(x.get("table_name") or x.get("table_id") or "") for x in items}),
            **data,
        })
    return out


def _summary_payload(user_id: int, range_name: str, table_id: str | None) -> dict[str, Any]:
    rows = _completed_player_rows(user_id, range_name, table_id)
    overall = _aggregate(rows)
    positions = _group_dimension(rows, lambda r: r.get("position") or "—")
    stacks = _group_dimension(rows, _stack_band)
    tables = _group_dimension(rows, lambda r: r.get("table_name") or r.get("table_id") or "—")
    return {
        "range": range_name,
        "table": table_id,
        "overall": overall,
        "positions": positions,
        "stack_bands": stacks,
        "tables": tables,
        "trend": _trend(rows),
        "sessions": _sessions(rows)[:20],
        "signals": _leak_signals(rows, overall, positions),
        "definitions": {
            "vpip": "プリフロップでブラインド以外のチップを自発的に投入した割合",
            "pfr": "プリフロップでレイズした割合",
            "three_bet": "3bet機会に対して3betした割合",
            "fold_to_three_bet": "自分のオープン後に3betを受けてフォールドした割合",
            "cbet": "プリフロップ最終アグレッサーとしてフロップでベット/レイズした割合",
            "wtsd": "フロップを見たハンドのうちショーダウンまで到達した割合",
            "wsd": "ショーダウン到達ハンドのうち勝った割合",
            "bb_per_100": "実収支を100ハンド換算した値。EVではありません",
        },
    }


def _can_view_hand(con, hand_id: str, user_id: int) -> bool:
    return bool(con.execute(
        "SELECT 1 FROM jj_hand_players WHERE hand_id=? AND user_id=?",
        (hand_id, user_id),
    ).fetchone())


def _visible_cards(player: dict[str, Any], viewer_id: int) -> list[str]:
    cards = list(_loads(player.get("hole_cards_json"), []))
    if int(player["user_id"]) == int(viewer_id) or _as_int(player.get("went_showdown")):
        return cards
    return ["??", "??"] if cards else []


def _detail_payload(hand_id: str, viewer_id: int) -> dict[str, Any]:
    with _DB.connect() as con:
        hand_row = con.execute(
            "SELECT * FROM jj_hand_history WHERE hand_id=?",
            (hand_id,),
        ).fetchone()
        if not hand_row or not _can_view_hand(con, hand_id, viewer_id):
            raise HTTPException(404, "hand not found")
        players = [
            dict(r) for r in con.execute(
                "SELECT * FROM jj_hand_players WHERE hand_id=? ORDER BY seat",
                (hand_id,),
            ).fetchall()
        ]
        actions = [
            dict(r) for r in con.execute(
                "SELECT * FROM jj_hand_actions WHERE hand_id=? ORDER BY seq",
                (hand_id,),
            ).fetchall()
        ]
        snapshots = [
            dict(r) for r in con.execute(
                "SELECT seq,street,state_json,created_at FROM jj_hand_snapshots WHERE hand_id=? ORDER BY seq",
                (hand_id,),
            ).fetchall()
        ]
        review = con.execute(
            "SELECT bookmarked,note,tags_json,updated_at FROM jj_hand_reviews WHERE hand_id=? AND user_id=?",
            (hand_id, viewer_id),
        ).fetchone()

    hand = dict(hand_row)
    hand["board"] = _loads(hand.pop("board_json", "[]"), [])
    hand["summary"] = _loads(hand.pop("summary_json", "{}"), {})
    for p in players:
        p["cards"] = _visible_cards(p, viewer_id)
        p.pop("hole_cards_json", None)
    for snap in snapshots:
        snap["state"] = _loads(snap.pop("state_json", "{}"), {})
    return {
        "hand": hand,
        "players": players,
        "actions": actions,
        "snapshots": snapshots,
        "review": {
            "bookmarked": bool(review["bookmarked"]) if review else False,
            "note": str(review["note"] or "") if review else "",
            "tags": _loads(review["tags_json"], []) if review else [],
            "updated_at": review["updated_at"] if review else None,
        },
    }


def _hand_list(
    user_id: int,
    *,
    limit: int,
    offset: int,
    range_name: str,
    position: str | None,
    result: str,
    showdown: str,
    street: str | None,
    table_id: str | None,
    bookmarked: bool,
    query: str,
) -> dict[str, Any]:
    where = ["p.user_id=?", "h.completed_at IS NOT NULL"]
    params: list[Any] = [user_id]
    start = _range_start(range_name)
    if start:
        where.append("h.completed_at>=?")
        params.append(start)
    if position:
        where.append("p.position=?")
        params.append(position)
    if result == "win":
        where.append("COALESCE(p.net_chips,0)>0")
    elif result == "loss":
        where.append("COALESCE(p.net_chips,0)<0")
    elif result == "even":
        where.append("COALESCE(p.net_chips,0)=0")
    if showdown == "yes":
        where.append("COALESCE(p.went_showdown,0)=1")
    elif showdown == "no":
        where.append("COALESCE(p.went_showdown,0)=0")
    if street:
        order = {"preflop": 0, "flop": 1, "turn": 2, "river": 3}
        if street in order:
            allowed = [k for k, v in order.items() if v >= order[street]]
            where.append("h.reached_street IN (" + ",".join("?" for _ in allowed) + ")")
            params.extend(allowed)
    if table_id:
        where.append("h.table_id=?")
        params.append(table_id)
    if bookmarked:
        where.append("COALESCE(rv.bookmarked,0)=1")
    q = (query or "").strip().lower()
    if q:
        where.append("(lower(h.hand_id) LIKE ? OR lower(h.table_name) LIKE ? OR lower(p.position) LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like, like])
    sql_where = " AND ".join(where)
    with _DB.connect() as con:
        count = con.execute(
            f"""SELECT COUNT(*) c FROM jj_hand_players p
                JOIN jj_hand_history h ON h.hand_id=p.hand_id
                LEFT JOIN jj_hand_reviews rv ON rv.hand_id=p.hand_id AND rv.user_id=p.user_id
                WHERE {sql_where}""",
            params,
        ).fetchone()
        rows = con.execute(
            f"""SELECT h.hand_id,h.table_id,h.table_name,h.hand_no,h.started_at,h.completed_at,
                       h.board_json,h.reached_street,h.result_type,h.showdown,h.partial_capture,h.player_count,
                       p.position,p.hole_cards_json,p.starting_stack_bb,p.effective_stack_bb,
                       p.net_chips,p.net_bb,p.won_hand,p.went_showdown,
                       COALESCE(rv.bookmarked,0) bookmarked,COALESCE(rv.tags_json,'[]') tags_json
                FROM jj_hand_players p JOIN jj_hand_history h ON h.hand_id=p.hand_id
                LEFT JOIN jj_hand_reviews rv ON rv.hand_id=p.hand_id AND rv.user_id=p.user_id
                WHERE {sql_where}
                ORDER BY h.completed_at DESC LIMIT ? OFFSET ?""",
            params + [limit, offset],
        ).fetchall()
    items = []
    for row in rows:
        d = dict(row)
        d["board"] = _loads(d.pop("board_json", "[]"), [])
        d["cards"] = _loads(d.pop("hole_cards_json", "[]"), [])
        d["tags"] = _loads(d.pop("tags_json", "[]"), [])
        d["bookmarked"] = bool(d["bookmarked"])
        d["won_hand"] = bool(d["won_hand"])
        d["went_showdown"] = bool(d["went_showdown"])
        d["partial_capture"] = bool(d["partial_capture"])
        items.append(d)
    return {"total": _as_int(count["c"] if count else 0), "limit": limit, "offset": offset, "items": items}


def _clean_tags(tags: list[str]) -> list[str]:
    out = []
    seen = set()
    for value in tags:
        tag = re.sub(r"\s+", " ", str(value or "").strip())[:30]
        if not tag or tag.lower() in seen:
            continue
        seen.add(tag.lower())
        out.append(tag)
        if len(out) >= 12:
            break
    return out


def _format_amount(chips: Any, bb: int) -> str:
    n = _as_int(chips)
    value = n / max(1, bb)
    return f"{n} ({value:g}bb)"


def _export_text(hand_id: str, viewer_id: int) -> str:
    data = _detail_payload(hand_id, viewer_id)
    hand = data["hand"]
    players = data["players"]
    actions = data["actions"]
    bb = max(1, _as_int(hand.get("big_blind"), 1))
    sb = _as_int(hand.get("small_blind"))
    started = str(hand.get("started_at") or "")
    lines = [
        f"JJ Arena Hand #{hand_id}: Hold'em No Limit ({sb}/{bb}) - {started}",
        f"Table '{hand.get('table_name') or hand.get('table_id')}' {hand.get('player_count')}max Seat #{_as_int(hand.get('button_seat'))+1} is the button",
    ]
    for p in players:
        lines.append(f"Seat {_as_int(p.get('seat'))+1}: {p.get('player_name')} ({_format_amount(p.get('starting_stack'), bb)} in chips) [{p.get('position')}]")
    sbp = next((p for p in players if _as_int(p.get("seat")) == _as_int(hand.get("small_blind_seat"), -999)), None)
    bbp = next((p for p in players if _as_int(p.get("seat")) == _as_int(hand.get("big_blind_seat"), -999)), None)
    if sbp:
        lines.append(f"{sbp.get('player_name')}: posts small blind {sb}")
    if bbp:
        lines.append(f"{bbp.get('player_name')}: posts big blind {bb}")
    lines += ["*** HOLE CARDS ***"]
    hero = next(p for p in players if int(p["user_id"]) == int(viewer_id))
    cards = hero.get("cards") or []
    if cards:
        lines.append(f"Dealt to {hero.get('player_name')} [{' '.join(cards)}]")

    board = list(hand.get("board") or [])
    current_street = "preflop"
    for a in actions:
        street = str(a.get("street") or "preflop")
        if street != current_street:
            if street == "flop":
                lines.append(f"*** FLOP *** [{' '.join(board[:3])}]")
            elif street == "turn":
                lines.append(f"*** TURN *** [{' '.join(board[:3])}] [{board[3] if len(board)>3 else ''}]")
            elif street == "river":
                lines.append(f"*** RIVER *** [{' '.join(board[:4])}] [{board[4] if len(board)>4 else ''}]")
            current_street = street
        name = str(a.get("player_name") or "")
        action = str(a.get("action") or "")
        if action == "fold":
            line = f"{name}: folds"
        elif action == "check":
            line = f"{name}: checks"
        elif action in {"call", "allin_call"}:
            line = f"{name}: calls {_as_int(a.get('amount_chips'))}"
            if action == "allin_call":
                line += " and is all-in"
        elif action in {"raise", "allin_raise"}:
            line = f"{name}: raises to {_as_int(a.get('to_chips'))}"
            if action == "allin_raise":
                line += " and is all-in"
        else:
            line = f"{name}: {action}"
        if _as_int(a.get("timed_out")):
            line += " [timeout]"
        lines.append(line)

    if hand.get("showdown"):
        lines.append("*** SHOW DOWN ***")
        for p in players:
            if _as_int(p.get("went_showdown")) and p.get("cards"):
                lines.append(f"{p.get('player_name')}: shows [{' '.join(p['cards'])}]")
    lines.append("*** SUMMARY ***")
    summary = hand.get("summary") or {}
    lines.append(f"Result: {summary.get('message') or hand.get('result_type') or 'complete'}")
    if board:
        lines.append(f"Board [{' '.join(board)}]")
    lines.append("JJ Arena Play Money — PokerStars-style text export (not affiliated with PokerStars)")
    return "\n".join(lines) + "\n"


def install(app, server, db) -> None:
    global _DB, _SERVER
    if getattr(app.state, "jj_hand_analytics_installed", False):
        return
    app.state.jj_hand_analytics_installed = True
    _DB, _SERVER = db, server
    _ensure_schema()
    _wrap_runtime()

    @app.get("/api/analysis/summary")
    def analysis_summary(
        range: str = Query(default="all", pattern="^(all|7d|30d|90d)$"),
        table: str | None = None,
        user=Depends(server.current_user),
    ):
        return _summary_payload(int(user["id"]), range, table)

    @app.get("/api/analysis/hands")
    def analysis_hands(
        limit: int = Query(default=40, ge=1, le=100),
        offset: int = Query(default=0, ge=0, le=100000),
        range: str = Query(default="all", pattern="^(all|7d|30d|90d)$"),
        position: str | None = Query(default=None, max_length=20),
        result: str = Query(default="all", pattern="^(all|win|loss|even)$"),
        showdown: str = Query(default="all", pattern="^(all|yes|no)$"),
        street: str | None = Query(default=None, pattern="^(preflop|flop|turn|river)$"),
        table: str | None = Query(default=None, max_length=80),
        bookmarked: bool = False,
        q: str = Query(default="", max_length=80),
        user=Depends(server.current_user),
    ):
        return _hand_list(
            int(user["id"]), limit=limit, offset=offset, range_name=range,
            position=position, result=result, showdown=showdown, street=street, table_id=table,
            bookmarked=bookmarked, query=q,
        )

    @app.get("/api/analysis/hands/{hand_id}")
    def analysis_hand_detail(hand_id: str, user=Depends(server.current_user)):
        return _detail_payload(hand_id, int(user["id"]))

    @app.put("/api/analysis/hands/{hand_id}/review")
    def analysis_hand_review(hand_id: str, payload: HandReviewIn, user=Depends(server.current_user)):
        uid = int(user["id"])
        tags = _clean_tags(payload.tags)
        with _DB.connect() as con:
            if not _can_view_hand(con, hand_id, uid):
                raise HTTPException(404, "hand not found")
            exists = con.execute(
                "SELECT 1 FROM jj_hand_reviews WHERE hand_id=? AND user_id=?",
                (hand_id, uid),
            ).fetchone()
            if exists:
                con.execute(
                    "UPDATE jj_hand_reviews SET bookmarked=?,note=?,tags_json=?,updated_at=? WHERE hand_id=? AND user_id=?",
                    (1 if payload.bookmarked else 0, payload.note.strip(), _json(tags), _now(), hand_id, uid),
                )
            else:
                con.execute(
                    "INSERT INTO jj_hand_reviews(hand_id,user_id,bookmarked,note,tags_json,updated_at) VALUES (?,?,?,?,?,?)",
                    (hand_id, uid, 1 if payload.bookmarked else 0, payload.note.strip(), _json(tags), _now()),
                )
        return {"ok": True, "bookmarked": payload.bookmarked, "note": payload.note.strip(), "tags": tags}

    @app.get("/api/analysis/sessions")
    def analysis_sessions(
        range: str = Query(default="all", pattern="^(all|7d|30d|90d)$"),
        table: str | None = None,
        user=Depends(server.current_user),
    ):
        return {"sessions": _sessions(_completed_player_rows(int(user["id"]), range, table))}

    @app.get("/api/analysis/hands/{hand_id}/export.txt", response_class=PlainTextResponse)
    def analysis_export(hand_id: str, user=Depends(server.current_user)):
        return PlainTextResponse(
            _export_text(hand_id, int(user["id"])),
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="jj-{hand_id}.txt"'},
        )

    @app.get("/api/analysis/export.csv", response_class=PlainTextResponse)
    def analysis_csv(
        range: str = Query(default="all", pattern="^(all|7d|30d|90d)$"),
        user=Depends(server.current_user),
    ):
        rows = _completed_player_rows(int(user["id"]), range)
        header = "hand_id,completed_at,table,position,cards,effective_stack_bb,net_bb,vpip,pfr,three_bet,showdown,won\n"
        lines = [header.rstrip("\n")]
        for r in rows:
            cards = " ".join(_loads(r.get("hole_cards_json"), []))
            values = [
                r.get("hand_id"), r.get("completed_at"), r.get("table_name"),
                r.get("position"), cards, r.get("effective_stack_bb"), r.get("net_bb"),
                r.get("vpip"), r.get("pfr"), r.get("three_bet"), r.get("went_showdown"), r.get("won_hand"),
            ]
            lines.append(",".join('"' + str(v if v is not None else "").replace('"', '""') + '"' for v in values))
        return PlainTextResponse(
            "\n".join(lines) + "\n",
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="jj-hand-analysis.csv"'},
        )

    print("JJ_HAND_ANALYTICS_READY")
