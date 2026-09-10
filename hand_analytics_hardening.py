from __future__ import annotations

import inspect
from collections import defaultdict
from typing import Any


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _action_name(action: dict[str, Any]) -> str:
    return str(action.get("action") or "")


def _is_voluntary_preflop(action: dict[str, Any]) -> bool:
    return _action_name(action) in {"call", "raise", "allin_call", "allin_raise"} and _as_int(action.get("amount_chips")) > 0


def _mark_partial_best_effort(analytics, hand_id: str) -> None:
    try:
        with analytics._DB.connect() as con:
            con.execute(
                "UPDATE jj_hand_history SET partial_capture=1 WHERE hand_id=?",
                (hand_id,),
            )
    except Exception:
        pass


def install(analytics, server) -> None:
    """Refine statistic semantics without touching the poker engine.

    The core analytics module deliberately stays isolated from gameplay. This
    hardening layer corrects edge-case definitions discovered during pre-release
    review and marks a hand partial when an action write itself fails.
    """
    if getattr(analytics, "_jj_stats_hardening_installed", False):
        return
    analytics._jj_stats_hardening_installed = True

    # Follow the server-authoritative action timer instead of assuming a fixed
    # duration. If the signature ever changes, keep the existing safe fallback.
    try:
        param = inspect.signature(server.arm_action_deadline).parameters.get("seconds")
        default = getattr(param, "default", inspect._empty)
        if default is not inspect._empty:
            seconds = float(default)
            if 5 <= seconds <= 300:
                analytics.DEFAULT_DECISION_SECONDS = seconds
    except Exception:
        pass

    base_compute = analytics._compute_flags
    base_record = analytics._record_action

    def refined_compute_flags(con, hand_id: str, state: dict[str, Any]):
        flags = base_compute(con, hand_id, state)
        player_rows = con.execute(
            "SELECT user_id,position FROM jj_hand_players WHERE hand_id=? ORDER BY seat",
            (hand_id,),
        ).fetchall()
        players = {int(r["user_id"]): dict(r) for r in player_rows}
        actions = [
            dict(r) for r in con.execute(
                "SELECT * FROM jj_hand_actions WHERE hand_id=? ORDER BY seq",
                (hand_id,),
            ).fetchall()
        ]
        by_street: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for action in actions:
            by_street[str(action.get("street") or "")].append(action)

        # Standard AF / aggression-frequency are postflop metrics. Reset the
        # counters produced by the base implementation and count flop+ only.
        for uid in flags:
            flags[uid]["aggressive_actions"] = 0
            flags[uid]["call_actions"] = 0
            flags[uid]["check_actions"] = 0
        for street in ("flop", "turn", "river"):
            for action in by_street.get(street, []):
                uid = int(action["user_id"])
                if uid not in flags:
                    continue
                if _as_int(action.get("is_aggressive")):
                    flags[uid]["aggressive_actions"] += 1
                elif _action_name(action) in {"call", "allin_call"}:
                    flags[uid]["call_actions"] += 1
                elif _action_name(action) == "check":
                    flags[uid]["check_actions"] += 1

        pre = by_street.get("preflop", [])

        # A steal requires an unopened pot. A limp is voluntary action and
        # therefore closes the steal opportunity even when no raise occurred.
        for uid in flags:
            flags[uid]["steal_opp"] = 0
            flags[uid]["steal_attempt"] = 0
            flags[uid]["bb_vs_steal"] = 0
            flags[uid]["folded_bb_to_steal"] = 0
        unopened = True
        steal_opener = None
        steal_seq = None
        for action in pre:
            uid = int(action["user_id"])
            pos = str(players.get(uid, {}).get("position") or "")
            if unopened and pos in {"CO", "BTN", "BTN/SB", "SB"}:
                flags[uid]["steal_opp"] = 1
            if unopened and _as_int(action.get("is_aggressive")) and pos in {"CO", "BTN", "BTN/SB", "SB"}:
                flags[uid]["steal_attempt"] = 1
                steal_opener = uid
                steal_seq = int(action["seq"])
            if _is_voluntary_preflop(action):
                unopened = False

        if steal_opener is not None and steal_seq is not None:
            bb_uid = next((uid for uid, row in players.items() if str(row.get("position")) == "BB"), None)
            if bb_uid is not None and bb_uid != steal_opener:
                response = next(
                    (
                        action for action in pre
                        if int(action["user_id"]) == bb_uid and int(action["seq"]) > steal_seq
                    ),
                    None,
                )
                if response is not None:
                    flags[bb_uid]["bb_vs_steal"] = 1
                    flags[bb_uid]["folded_bb_to_steal"] = int(_action_name(response) == "fold")

        # A flop continuation-bet opportunity exists only when nobody has bet
        # before the preflop final aggressor's first flop decision. Raising a
        # donk lead is aggression, but it is not a continuation bet.
        for uid in flags:
            flags[uid]["cbet_opp"] = 0
            flags[uid]["cbet"] = 0
            flags[uid]["faced_cbet"] = 0
            flags[uid]["folded_to_cbet"] = 0
        pre_aggressors = [action for action in pre if _as_int(action.get("is_aggressive"))]
        pfr_uid = int(pre_aggressors[-1]["user_id"]) if pre_aggressors else None
        flop = by_street.get("flop", [])
        if pfr_uid in flags and flags[pfr_uid].get("saw_flop"):
            hero_index = next((i for i, action in enumerate(flop) if int(action["user_id"]) == pfr_uid), None)
            if hero_index is not None:
                prior = flop[:hero_index]
                faced_lead = any(_as_int(action.get("is_aggressive")) for action in prior)
                if not faced_lead:
                    flags[pfr_uid]["cbet_opp"] = 1
                    hero_action = flop[hero_index]
                    if _as_int(hero_action.get("is_aggressive")):
                        flags[pfr_uid]["cbet"] = 1
                        cbet_seq = int(hero_action["seq"])
                        for uid in flags:
                            if uid == pfr_uid or not flags[uid].get("saw_flop"):
                                continue
                            response = next(
                                (
                                    action for action in flop
                                    if int(action["user_id"]) == uid and int(action["seq"]) > cbet_seq
                                ),
                                None,
                            )
                            if response is not None:
                                flags[uid]["faced_cbet"] = 1
                                flags[uid]["folded_to_cbet"] = int(_action_name(response) == "fold")
        return flags

    def robust_record_action(context: dict[str, Any]) -> None:
        try:
            base_record(context)
        except Exception:
            _mark_partial_best_effort(analytics, str(context.get("hand_id") or ""))
            raise

    analytics._compute_flags = refined_compute_flags
    analytics._record_action = robust_record_action
