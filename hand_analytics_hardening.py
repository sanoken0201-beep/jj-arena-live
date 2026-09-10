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


def _is_aggressive(action: dict[str, Any]) -> bool:
    return bool(_as_int(action.get("is_aggressive")))


def _first_response_after(actions: list[dict[str, Any]], user_id: int, seq: int) -> dict[str, Any] | None:
    return next(
        (a for a in actions if int(a["user_id"]) == int(user_id) and int(a["seq"]) > int(seq)),
        None,
    )


def _intervening_aggression(actions: list[dict[str, Any]], start_seq: int, end_seq: int) -> bool:
    return any(
        int(start_seq) < int(a["seq"]) < int(end_seq) and _is_aggressive(a)
        for a in actions
    )


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
    """Refine statistic semantics without changing poker-engine decisions.

    This layer exists so statistic-definition fixes remain isolated from the
    engine. It also makes analytics failure non-authoritative: gameplay can
    continue and an incomplete hand is excluded from aggregate statistics.
    """
    if getattr(analytics, "_jj_stats_hardening_installed", False):
        return
    analytics._jj_stats_hardening_installed = True

    # Follow the server-authoritative action timer instead of assuming a fixed
    # duration. If the signature ever changes, retain the core safe fallback.
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

        # AF and the displayed aggressive-action percentage are postflop only.
        for uid in flags:
            flags[uid]["aggressive_actions"] = 0
            flags[uid]["call_actions"] = 0
            flags[uid]["check_actions"] = 0
        for street in ("flop", "turn", "river"):
            for action in by_street.get(street, []):
                uid = int(action["user_id"])
                if uid not in flags:
                    continue
                if _is_aggressive(action):
                    flags[uid]["aggressive_actions"] += 1
                elif _action_name(action) in {"call", "allin_call"}:
                    flags[uid]["call_actions"] += 1
                elif _action_name(action) == "check":
                    flags[uid]["check_actions"] += 1

        pre = by_street.get("preflop", [])

        # Recompute 3bet denominators. Every distinct player whose first action
        # after the opening raise occurs before a 3bet has a genuine 3bet
        # opportunity. A caller/folder in between must not hide the later
        # player's squeeze opportunity.
        for uid in flags:
            flags[uid]["three_bet_opp"] = 0
            flags[uid]["three_bet"] = 0
            flags[uid]["faced_three_bet"] = 0
            flags[uid]["folded_to_three_bet"] = 0
        opener_action = next(
            (a for a in pre if _is_aggressive(a) and _as_int(a.get("raise_number")) == 1),
            None,
        )
        if opener_action is not None:
            opener = int(opener_action["user_id"])
            opener_seq = int(opener_action["seq"])
            seen: set[int] = set()
            three_bettor = None
            three_bet_seq = None
            for action in pre:
                if int(action["seq"]) <= opener_seq:
                    continue
                uid = int(action["user_id"])
                if uid == opener or uid in seen:
                    continue
                seen.add(uid)
                if uid in flags:
                    flags[uid]["three_bet_opp"] = 1
                if _is_aggressive(action) and _as_int(action.get("raise_number")) == 2:
                    three_bettor = uid
                    three_bet_seq = int(action["seq"])
                    if uid in flags:
                        flags[uid]["three_bet"] = 1
                    break
            if three_bettor is not None and three_bet_seq is not None and opener in flags:
                flags[opener]["faced_three_bet"] = 1
                response = _first_response_after(pre, opener, three_bet_seq)
                if response is not None and not _intervening_aggression(pre, three_bet_seq, int(response["seq"])):
                    flags[opener]["folded_to_three_bet"] = int(_action_name(response) == "fold")

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
            if unopened and pos in {"CO", "BTN", "BTN/SB", "SB"} and uid in flags:
                flags[uid]["steal_opp"] = 1
            if unopened and _is_aggressive(action) and pos in {"CO", "BTN", "BTN/SB", "SB"}:
                if uid in flags:
                    flags[uid]["steal_attempt"] = 1
                steal_opener = uid
                steal_seq = int(action["seq"])
            if _is_voluntary_preflop(action):
                unopened = False

        if steal_opener is not None and steal_seq is not None:
            bb_uid = next((uid for uid, row in players.items() if str(row.get("position")) == "BB"), None)
            if bb_uid is not None and bb_uid != steal_opener:
                response = _first_response_after(pre, bb_uid, steal_seq)
                if response is not None and not _intervening_aggression(pre, steal_seq, int(response["seq"])):
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
        pre_aggressors = [action for action in pre if _is_aggressive(action)]
        pfr_uid = int(pre_aggressors[-1]["user_id"]) if pre_aggressors else None
        flop = by_street.get("flop", [])
        if pfr_uid in flags and flags[pfr_uid].get("saw_flop"):
            hero_index = next((i for i, action in enumerate(flop) if int(action["user_id"]) == pfr_uid), None)
            if hero_index is not None:
                prior = flop[:hero_index]
                faced_lead = any(_is_aggressive(action) for action in prior)
                if not faced_lead:
                    flags[pfr_uid]["cbet_opp"] = 1
                    hero_action = flop[hero_index]
                    if _is_aggressive(hero_action):
                        flags[pfr_uid]["cbet"] = 1
                        cbet_seq = int(hero_action["seq"])
                        for uid in flags:
                            if uid == pfr_uid or not flags[uid].get("saw_flop"):
                                continue
                            response = _first_response_after(flop, uid, cbet_seq)
                            if response is None:
                                continue
                            # If another player raised before this player's
                            # response, that response is no longer directly to
                            # the original cbet and is excluded from the metric.
                            if _intervening_aggression(flop, cbet_seq, int(response["seq"])):
                                continue
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
