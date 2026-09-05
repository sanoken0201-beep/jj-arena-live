from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
import random
from typing import Any

RANKS = "23456789TJQKA"
SUITS = "cdhs"
RANK_VALUE = {r: i + 2 for i, r in enumerate(RANKS)}
CATEGORY_NAMES = [
    "High Card",
    "One Pair",
    "Two Pair",
    "Three of a Kind",
    "Straight",
    "Flush",
    "Full House",
    "Four of a Kind",
    "Straight Flush",
]


def bb_text(state: dict[str, Any], amount: int | float) -> str:
    bb = max(1, int(state.get("big_blind", 1)))
    value = float(amount) / bb
    return f"{value:g}bb"


def new_deck() -> list[str]:
    deck = [r + s for r in RANKS for s in SUITS]
    random.SystemRandom().shuffle(deck)
    return deck


def rank_five(cards: list[str]) -> tuple:
    if len(cards) != 5:
        raise ValueError("rank_five requires exactly five cards")
    vals = sorted((RANK_VALUE[c[0]] for c in cards), reverse=True)
    suits = [c[1] for c in cards]
    flush = len(set(suits)) == 1
    unique = sorted(set(vals), reverse=True)
    if unique == [14, 5, 4, 3, 2]:
        straight_high = 5
    elif len(unique) == 5 and unique[0] - unique[4] == 4:
        straight_high = unique[0]
    else:
        straight_high = None

    counts: dict[int, int] = {}
    for v in vals:
        counts[v] = counts.get(v, 0) + 1
    groups = sorted(((cnt, val) for val, cnt in counts.items()), reverse=True)

    if flush and straight_high:
        return (8, straight_high)
    if groups[0][0] == 4:
        four = groups[0][1]
        kicker = max(v for v in vals if v != four)
        return (7, four, kicker)
    if sorted(counts.values()) == [2, 3]:
        trip = max(v for v, c in counts.items() if c == 3)
        pair = max(v for v, c in counts.items() if c == 2)
        return (6, trip, pair)
    if flush:
        return (5, *vals)
    if straight_high:
        return (4, straight_high)
    if groups[0][0] == 3:
        trip = groups[0][1]
        kickers = sorted((v for v in vals if v != trip), reverse=True)
        return (3, trip, *kickers)
    pairs = sorted((v for v, c in counts.items() if c == 2), reverse=True)
    if len(pairs) >= 2:
        high_pair, low_pair = pairs[:2]
        kicker = max(v for v in vals if v not in (high_pair, low_pair))
        return (2, high_pair, low_pair, kicker)
    if len(pairs) == 1:
        pair = pairs[0]
        kickers = sorted((v for v in vals if v != pair), reverse=True)
        return (1, pair, *kickers)
    return (0, *vals)


def rank_seven(cards: list[str]) -> tuple:
    if len(cards) < 5:
        raise ValueError("at least five cards required")
    return max(rank_five(list(c)) for c in combinations(cards, 5))


def hand_name(score: tuple) -> str:
    return CATEGORY_NAMES[score[0]]


def next_live_seat(seats: list[dict[str, Any]], after: int, predicate) -> int | None:
    occupied = {p["seat"]: p for p in seats}
    if not occupied:
        return None
    max_seat = max(max(occupied), max((p.get("max_seats", 0) for p in seats), default=0))
    span = max(max_seat + 1, 2)
    for step in range(1, span + 1):
        seat = (after + step) % span
        p = occupied.get(seat)
        if p and predicate(p):
            return seat
    return None


def _find_player(state: dict[str, Any], user_id: int) -> dict[str, Any]:
    for p in state["seats"]:
        if p["user_id"] == user_id:
            return p
    raise ValueError("player is not seated")


def _next_seat(state: dict[str, Any], after: int, predicate) -> int | None:
    occupied = {p["seat"]: p for p in state["seats"]}
    for step in range(1, state["max_seats"] + 1):
        seat = (after + step) % state["max_seats"]
        p = occupied.get(seat)
        if p and predicate(p):
            return seat
    return None


def _in_hand_players(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [p for p in state["seats"] if p.get("in_hand") and not p.get("folded")]


def _can_act(p: dict[str, Any]) -> bool:
    return p.get("in_hand") and not p.get("folded") and not p.get("all_in") and p.get("stack", 0) > 0


def _needs_action(state: dict[str, Any], p: dict[str, Any]) -> bool:
    if not _can_act(p):
        return False
    return p["user_id"] not in state["hand"]["acted"] or p.get("round_bet", 0) != state["hand"]["current_bet"]


def _take_from_stack(p: dict[str, Any], amount: int) -> int:
    amount = max(0, min(int(amount), int(p["stack"])))
    p["stack"] -= amount
    p["round_bet"] += amount
    p["contributed"] += amount
    if p["stack"] == 0:
        p["all_in"] = True
    return amount


def _post_blind(p: dict[str, Any], amount: int) -> int:
    return _take_from_stack(p, amount)


def blank_table_state(*, table_id: str, name: str, max_seats: int = 6, small_blind: int = 5, big_blind: int = 10, min_buyin: int = 500, max_buyin: int = 5000, owner_id: int | None = None) -> dict[str, Any]:
    return {"id": table_id, "name": name, "max_seats": max(2, min(9, int(max_seats))), "small_blind": max(1, int(small_blind)), "big_blind": max(int(small_blind), int(big_blind)), "min_buyin": max(1, int(min_buyin)), "max_buyin": max(int(min_buyin), int(max_buyin)), "owner_id": owner_id, "status": "waiting", "button_seat": -1, "seats": [], "hand": None, "hand_no": 0, "last_result": None}


def seat_player(state: dict[str, Any], *, user_id: int, name: str, seat: int, stack: int) -> None:
    if state["status"] == "playing": raise ValueError("cannot take a seat during an active hand")
    if not 0 <= seat < state["max_seats"]: raise ValueError("invalid seat")
    if any(p["seat"] == seat for p in state["seats"]): raise ValueError("seat is occupied")
    if any(p["user_id"] == user_id for p in state["seats"]): raise ValueError("already seated")
    if not state["min_buyin"] <= stack <= state["max_buyin"]: raise ValueError("buy-in is outside table limits")
    state["seats"].append({"user_id": user_id, "name": name, "seat": seat, "stack": int(stack), "in_hand": False, "folded": False, "all_in": False, "round_bet": 0, "contributed": 0, "cards": []})
    state["seats"].sort(key=lambda p: p["seat"])


def remove_player(state: dict[str, Any], user_id: int) -> int:
    p = _find_player(state, user_id)
    if state["status"] == "playing" and p.get("in_hand"): raise ValueError("cannot leave while participating in a hand")
    chips = int(p["stack"])
    state["seats"] = [x for x in state["seats"] if x["user_id"] != user_id]
    return chips


def start_hand(state: dict[str, Any]) -> None:
    eligible = [p for p in state["seats"] if p["stack"] > 0]
    if state["status"] == "playing": raise ValueError("hand already in progress")
    if len(eligible) < 2: raise ValueError("at least two players with chips are required")
    for p in state["seats"]:
        p.update({"in_hand": p["stack"] > 0, "folded": False, "all_in": False, "round_bet": 0, "contributed": 0, "cards": []})
    state["hand_no"] += 1
    deck = new_deck()
    state["button_seat"] = _next_seat(state, state.get("button_seat", -1), lambda p: p["stack"] > 0)
    button = state["button_seat"]
    if len(eligible) == 2:
        sb_seat = button; bb_seat = _next_seat(state, sb_seat, lambda p: p["stack"] > 0)
    else:
        sb_seat = _next_seat(state, button, lambda p: p["stack"] > 0); bb_seat = _next_seat(state, sb_seat, lambda p: p["stack"] > 0)
    for _ in range(2):
        for p in sorted(eligible, key=lambda x: ((x["seat"] - button) % state["max_seats"])): p["cards"].append(deck.pop())
    sb = next(p for p in state["seats"] if p["seat"] == sb_seat); bb = next(p for p in state["seats"] if p["seat"] == bb_seat)
    _post_blind(sb, state["small_blind"]); _post_blind(bb, state["big_blind"])
    state["hand"] = {"id": f"{state['id']}-{state['hand_no']}", "phase": "preflop", "deck": deck, "board": [], "current_bet": max(sb["round_bet"], bb["round_bet"], state["big_blind"]), "min_raise": state["big_blind"], "acted": [], "raise_closed_for": [], "action_seat": None, "small_blind_seat": sb_seat, "big_blind_seat": bb_seat, "log": [f"Hand #{state['hand_no']} started"], "showdown": None}
    state["status"] = "playing"
    _set_next_action(state, bb_seat); _auto_progress_if_needed(state)


def _set_next_action(state: dict[str, Any], after: int) -> None:
    state["hand"]["action_seat"] = _next_seat(state, after, lambda p: _needs_action(state, p))


def _round_complete(state: dict[str, Any]) -> bool:
    hand = state["hand"]
    for p in state["seats"]:
        if _can_act(p) and (p["user_id"] not in hand["acted"] or p["round_bet"] != hand["current_bet"]): return False
    return True


def _reset_round(state: dict[str, Any], phase: str) -> None:
    hand = state["hand"]
    for p in state["seats"]: p["round_bet"] = 0
    hand.update({"phase": phase, "current_bet": 0, "min_raise": state["big_blind"], "acted": [], "raise_closed_for": []})
    hand["action_seat"] = _next_seat(state, state["button_seat"], lambda p: _can_act(p))


def _deal_to_phase(state: dict[str, Any], phase: str) -> None:
    hand = state["hand"]; deck = hand["deck"]
    if phase == "flop":
        deck.pop(); hand["board"].extend([deck.pop(), deck.pop(), deck.pop()])
    elif phase in ("turn", "river"):
        deck.pop(); hand["board"].append(deck.pop())
    else: raise ValueError("unknown phase")
    _reset_round(state, phase); hand["log"].append(phase.upper())


def _advance_round(state: dict[str, Any]) -> None:
    phase = state["hand"]["phase"]
    if phase == "preflop": _deal_to_phase(state, "flop")
    elif phase == "flop": _deal_to_phase(state, "turn")
    elif phase == "turn": _deal_to_phase(state, "river")
    elif phase == "river": _showdown(state)


def _auto_progress_if_needed(state: dict[str, Any]) -> None:
    if state["status"] != "playing": return
    live = _in_hand_players(state)
    if len(live) == 1: _award_uncontested(state, live[0]); return
    actionable = [p for p in live if _can_act(p)]
    no_decision_left = len(actionable) == 0 or (len(actionable) == 1 and actionable[0].get("round_bet", 0) == state["hand"]["current_bet"])
    if no_decision_left:
        while state["status"] == "playing" and state["hand"]["phase"] != "river": _advance_round(state)
        if state["status"] == "playing": _showdown(state)
        return
    if _round_complete(state): _advance_round(state); _auto_progress_if_needed(state)


def legal_actions(state: dict[str, Any], user_id: int) -> dict[str, Any]:
    if state["status"] != "playing" or not state.get("hand"): return {"can_act": False}
    p = _find_player(state, user_id); hand = state["hand"]
    if hand["action_seat"] != p["seat"] or not _can_act(p): return {"can_act": False}
    call_amount = max(0, hand["current_bet"] - p["round_bet"]); max_to = p["round_bet"] + p["stack"]
    raise_closed = user_id in hand.get("raise_closed_for", []); can_raise = max_to > hand["current_bet"] and not raise_closed
    min_raise_to = hand["current_bet"] + hand["min_raise"] if can_raise else None
    return {"can_act": True, "call_amount": min(call_amount, p["stack"]), "can_check": call_amount == 0, "can_call": call_amount > 0, "can_raise": can_raise, "min_raise_to": min_raise_to if min_raise_to is not None and min_raise_to <= max_to else None, "max_raise_to": max_to, "can_all_in": p["stack"] > 0 and (not raise_closed or max_to <= hand["current_bet"])}


def apply_action(state: dict[str, Any], user_id: int, action: str, amount: int | None = None) -> None:
    if state["status"] != "playing" or not state.get("hand"): raise ValueError("no active hand")
    p = _find_player(state, user_id); hand = state["hand"]
    if hand["action_seat"] != p["seat"] or not _can_act(p): raise ValueError("not your turn")
    action = action.lower(); old_seat = p["seat"]; call_amount = max(0, hand["current_bet"] - p["round_bet"])
    if action == "fold":
        p["folded"] = True; hand["acted"].append(user_id); hand["log"].append(f"{p['name']} folds")
    elif action == "check":
        if call_amount != 0: raise ValueError("cannot check facing a bet")
        hand["acted"].append(user_id); hand["log"].append(f"{p['name']} checks")
    elif action == "call":
        if call_amount <= 0: raise ValueError("nothing to call")
        paid = _take_from_stack(p, call_amount); hand["acted"].append(user_id); hand["log"].append(f"{p['name']} calls {bb_text(state, paid)}")
    elif action in ("raise", "allin"):
        target = p["round_bet"] + p["stack"] if action == "allin" else int(amount or 0); max_to = p["round_bet"] + p["stack"]
        if target > max_to or target <= p["round_bet"]: raise ValueError("invalid raise amount")
        if target <= hand["current_bet"]:
            if target != max_to: raise ValueError("raise must exceed current bet")
            _take_from_stack(p, target - p["round_bet"]); hand["acted"].append(user_id); hand["log"].append(f"{p['name']} is all-in for {bb_text(state, p['round_bet'])}")
        else:
            if user_id in hand.get("raise_closed_for", []): raise ValueError("betting was not reopened by the short all-in")
            raise_size = target - hand["current_bet"]; full_raise = raise_size >= hand["min_raise"]
            if not full_raise and target != max_to: raise ValueError(f"minimum raise-to is {hand['current_bet'] + hand['min_raise']}")
            _take_from_stack(p, target - p["round_bet"]); previous = hand["current_bet"]; hand["current_bet"] = target
            if full_raise:
                hand["min_raise"] = target - previous; hand["acted"] = [user_id]; hand["raise_closed_for"] = []
            else:
                prior_acted = list(hand["acted"])
                if user_id not in hand["acted"]: hand["acted"].append(user_id)
                closed = set(hand.get("raise_closed_for", [])); closed.update(uid for uid in prior_acted if uid != user_id); hand["raise_closed_for"] = list(closed)
            hand["log"].append(f"{p['name']} {'raises to' if action == 'raise' else 'is all-in to'} {bb_text(state, target)}")
    else: raise ValueError("unknown action")
    live = _in_hand_players(state)
    if len(live) == 1: _award_uncontested(state, live[0]); return
    if _round_complete(state): _advance_round(state); _auto_progress_if_needed(state)
    else: _set_next_action(state, old_seat); _auto_progress_if_needed(state)


def _award_uncontested(state: dict[str, Any], winner: dict[str, Any]) -> None:
    total = sum(int(p.get("contributed", 0)) for p in state["seats"]); winner["stack"] += total
    state["last_result"] = {"type": "uncontested", "winners": [{"user_id": winner["user_id"], "name": winner["name"], "amount": total}], "board": list(state["hand"]["board"]), "message": f"{winner['name']} wins {bb_text(state, total)}"}
    _finish_hand(state)


def _build_side_pots(state: dict[str, Any]) -> list[dict[str, Any]]:
    contributors = [p for p in state["seats"] if p.get("contributed", 0) > 0]; levels = sorted(set(int(p["contributed"]) for p in contributors)); pots = []; prev = 0
    for level in levels:
        involved = [p for p in contributors if p["contributed"] >= level]; amount = (level - prev) * len(involved); eligible = [p for p in involved if p.get("in_hand") and not p.get("folded")]
        if amount > 0: pots.append({"amount": amount, "eligible": eligible})
        prev = level
    return pots


def _showdown(state: dict[str, Any]) -> None:
    hand = state["hand"]; board = list(hand["board"])
    while len(board) < 5:
        if len(board) == 0:
            hand["deck"].pop(); board.extend([hand["deck"].pop(), hand["deck"].pop(), hand["deck"].pop()])
        else:
            hand["deck"].pop(); board.append(hand["deck"].pop())
    hand["board"] = board
    scores = {p["user_id"]: rank_seven(p["cards"] + board) for p in _in_hand_players(state)}; awards: dict[int, int] = {}; pot_results = []
    for pot in _build_side_pots(state):
        elig = pot["eligible"]
        if not elig: continue
        best = max(scores[p["user_id"]] for p in elig); winners = [p for p in elig if scores[p["user_id"]] == best]; share, rem = divmod(pot["amount"], len(winners))
        winners = sorted(winners, key=lambda p: ((p["seat"] - state["button_seat"]) % state["max_seats"]))
        for i, p in enumerate(winners):
            amt = share + (1 if i < rem else 0); p["stack"] += amt; awards[p["user_id"]] = awards.get(p["user_id"], 0) + amt
        pot_results.append({"amount": pot["amount"], "winners": [{"user_id": p["user_id"], "name": p["name"]} for p in winners], "hand": hand_name(best)})
    winners_payload = []
    for p in state["seats"]:
        if p["user_id"] in awards:
            winners_payload.append({"user_id": p["user_id"], "name": p["name"], "amount": awards[p["user_id"]], "hand": hand_name(scores[p["user_id"]]), "cards": list(p["cards"])})
    msg = ", ".join(f"{w['name']} +{bb_text(state, w['amount'])} ({w['hand']})" for w in winners_payload)
    hand["showdown"] = {"scores": {str(uid): list(score) for uid, score in scores.items()}, "pots": pot_results}
    state["last_result"] = {"type": "showdown", "winners": winners_payload, "board": board, "message": msg or "Showdown complete"}
    _finish_hand(state)


def _finish_hand(state: dict[str, Any]) -> None:
    hand = state.get("hand")
    if hand: hand["phase"] = "complete"; hand["action_seat"] = None
    for p in state["seats"]: p["in_hand"] = False; p["folded"] = False; p["all_in"] = False; p["round_bet"] = 0; p["contributed"] = 0
    state["status"] = "waiting"


def public_state(state: dict[str, Any], viewer_id: int | None = None) -> dict[str, Any]:
    out = {k: v for k, v in state.items() if k not in ("seats", "hand")}; reveal_all = bool(state.get("hand") and state["hand"].get("phase") == "complete"); out["seats"] = []
    for p in state["seats"]:
        item = {k: v for k, v in p.items() if k != "cards"}
        if p["user_id"] == viewer_id or reveal_all: item["cards"] = list(p.get("cards", []))
        elif p.get("in_hand"): item["cards"] = ["??", "??"]
        else: item["cards"] = []
        out["seats"].append(item)
    if state.get("hand"):
        h = {k: v for k, v in state["hand"].items() if k != "deck"}; h["acted"] = list(h.get("acted", [])); out["hand"] = h
    else: out["hand"] = None
    if viewer_id is not None:
        try: out["legal"] = legal_actions(state, viewer_id)
        except ValueError: out["legal"] = {"can_act": False}
    return out
