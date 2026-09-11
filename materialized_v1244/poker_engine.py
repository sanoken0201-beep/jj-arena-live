from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
import random
import uuid
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
    # caller typically uses table max seats; fallback to occupied max + 1
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


def blank_table_state(
    *,
    table_id: str,
    name: str,
    max_seats: int = 6,
    small_blind: int = 5,
    big_blind: int = 10,
    min_buyin: int = 500,
    max_buyin: int = 5000,
    owner_id: int | None = None,
) -> dict[str, Any]:
    return {
        "id": table_id,
        "name": name,
        "max_seats": max(2, min(9, int(max_seats))),
        "small_blind": max(1, int(small_blind)),
        "big_blind": max(int(small_blind), int(big_blind)),
        "min_buyin": max(1, int(min_buyin)),
        "max_buyin": max(int(min_buyin), int(max_buyin)),
        "owner_id": owner_id,
        "status": "waiting",
        "button_seat": -1,
        "seats": [],
        "hand": None,
        "hand_no": 0,
        "last_result": None,
        "rake_percent": 0.10,
        "rake_cap": max(int(big_blind) * 5, 1),
    }


def seat_player(state: dict[str, Any], *, user_id: int, name: str, seat: int, stack: int) -> None:
    if state["status"] == "playing":
        raise ValueError("cannot take a seat during an active hand")
    if not 0 <= seat < state["max_seats"]:
        raise ValueError("invalid seat")
    if any(p["seat"] == seat for p in state["seats"]):
        raise ValueError("seat is occupied")
    if any(p["user_id"] == user_id for p in state["seats"]):
        raise ValueError("already seated")
    if not state["min_buyin"] <= stack <= state["max_buyin"]:
        raise ValueError("buy-in is outside table limits")
    state["seats"].append({
        "user_id": user_id,
        "name": name,
        "seat": seat,
        "stack": int(stack),
        "in_hand": False,
        "folded": False,
        "all_in": False,
        "round_bet": 0,
        "contributed": 0,
        "cards": [],
    })
    state["seats"].sort(key=lambda p: p["seat"])


def remove_player(state: dict[str, Any], user_id: int) -> int:
    p = _find_player(state, user_id)
    if state["status"] == "playing" and p.get("in_hand"):
        raise ValueError("cannot leave while participating in a hand")
    chips = int(p["stack"])
    state["seats"] = [x for x in state["seats"] if x["user_id"] != user_id]
    return chips


def start_hand(state: dict[str, Any]) -> None:
    eligible = [p for p in state["seats"] if p["stack"] > 0]
    if state["status"] == "playing":
        raise ValueError("hand already in progress")
    if len(eligible) < 2:
        raise ValueError("at least two players with chips are required")
    starting_stacks = {str(p["user_id"]): int(p["stack"]) for p in eligible}

    for p in state["seats"]:
        p.update({"in_hand": p["stack"] > 0, "folded": False, "all_in": False, "round_bet": 0, "contributed": 0, "cards": []})

    state["hand_no"] += 1
    deck = new_deck()
    state["button_seat"] = _next_seat(state, state.get("button_seat", -1), lambda p: p["stack"] > 0)
    button = state["button_seat"]
    active_count = len(eligible)
    if active_count == 2:
        sb_seat = button
        bb_seat = _next_seat(state, sb_seat, lambda p: p["stack"] > 0)
    else:
        sb_seat = _next_seat(state, button, lambda p: p["stack"] > 0)
        bb_seat = _next_seat(state, sb_seat, lambda p: p["stack"] > 0)

    for _ in range(2):
        for p in sorted(eligible, key=lambda x: ((x["seat"] - button) % state["max_seats"])):
            p["cards"].append(deck.pop())

    sb = next(p for p in state["seats"] if p["seat"] == sb_seat)
    bb = next(p for p in state["seats"] if p["seat"] == bb_seat)
    _post_blind(sb, state["small_blind"])
    _post_blind(bb, state["big_blind"])

    state["hand"] = {
        "id": f"{state['id']}-{state['hand_no']}-{uuid.uuid4().hex[:10]}",
        "phase": "preflop",
        "deck": deck,
        "board": [],
        "current_bet": max(sb["round_bet"], bb["round_bet"], state["big_blind"]),
        "min_raise": state["big_blind"],
        "acted": [],
        "raise_closed_for": [],
        "action_seat": None,
        "small_blind_seat": sb_seat,
        "big_blind_seat": bb_seat,
        "log": [f"Hand #{state['hand_no']} started"],
        "showdown": None,
        "starting_stacks": starting_stacks,
        "revealed_user_ids": [],
        "result_persisted": False,
    }
    state["status"] = "playing"
    _set_next_action(state, bb_seat)
    _auto_progress_if_needed(state)


def _set_next_action(state: dict[str, Any], after: int) -> None:
    hand = state["hand"]
    nxt = _next_seat(state, after, lambda p: _needs_action(state, p))
    hand["action_seat"] = nxt


def _round_complete(state: dict[str, Any]) -> bool:
    hand = state["hand"]
    for p in state["seats"]:
        if _can_act(p):
            if p["user_id"] not in hand["acted"] or p["round_bet"] != hand["current_bet"]:
                return False
    return True


def _reset_round(state: dict[str, Any], phase: str) -> None:
    hand = state["hand"]
    for p in state["seats"]:
        p["round_bet"] = 0
    hand["phase"] = phase
    hand["current_bet"] = 0
    hand["min_raise"] = state["big_blind"]
    hand["acted"] = []
    hand["raise_closed_for"] = []
    hand["action_seat"] = _next_seat(state, state["button_seat"], lambda p: _can_act(p))


def _deal_to_phase(state: dict[str, Any], phase: str) -> None:
    hand = state["hand"]
    deck = hand["deck"]
    if phase == "flop":
        deck.pop()  # burn
        hand["board"].extend([deck.pop(), deck.pop(), deck.pop()])
    elif phase in ("turn", "river"):
        deck.pop()
        hand["board"].append(deck.pop())
    else:
        raise ValueError("unknown phase")
    _reset_round(state, phase)
    hand["log"].append(phase.upper())


def _advance_round(state: dict[str, Any]) -> None:
    hand = state["hand"]
    phase = hand["phase"]
    if phase == "preflop":
        _deal_to_phase(state, "flop")
    elif phase == "flop":
        _deal_to_phase(state, "turn")
    elif phase == "turn":
        _deal_to_phase(state, "river")
    elif phase == "river":
        _showdown(state)


def _auto_progress_if_needed(state: dict[str, Any]) -> None:
    if state["status"] != "playing":
        return
    live = _in_hand_players(state)
    if len(live) == 1:
        _award_uncontested(state, live[0])
        return
    actionable = [p for p in live if _can_act(p)]
    # With nobody able to act, run the board. With exactly one actionable
    # player, run it only when that player has no outstanding call; otherwise
    # that player must still choose call/fold.
    no_decision_left = len(actionable) == 0 or (
        len(actionable) == 1
        and actionable[0].get("round_bet", 0) == state["hand"]["current_bet"]
    )
    if no_decision_left:
        while state["status"] == "playing" and state["hand"]["phase"] != "river":
            _advance_round(state)
        if state["status"] == "playing":
            _showdown(state)
        return
    if _round_complete(state):
        _advance_round(state)
        _auto_progress_if_needed(state)


def legal_actions(state: dict[str, Any], user_id: int) -> dict[str, Any]:
    if state["status"] != "playing" or not state.get("hand"):
        return {"can_act": False}
    p = _find_player(state, user_id)
    hand = state["hand"]
    if hand["action_seat"] != p["seat"] or not _can_act(p):
        return {"can_act": False}
    call_amount = max(0, hand["current_bet"] - p["round_bet"])
    max_to = p["round_bet"] + p["stack"]
    raise_closed = user_id in hand.get("raise_closed_for", [])
    min_raise_to = hand["current_bet"] + hand["min_raise"]
    # A normal raise is legal only when the player can reach the full minimum.
    # A smaller increase is represented exclusively as an all-in action.
    can_raise = max_to >= min_raise_to and max_to > hand["current_bet"] and not raise_closed
    return {
        "can_act": True,
        "call_amount": min(call_amount, p["stack"]),
        "can_check": call_amount == 0,
        "can_call": call_amount > 0,
        "can_raise": can_raise,
        "min_raise_to": min_raise_to if can_raise else None,
        "max_raise_to": max_to,
        "can_all_in": p["stack"] > 0 and (not raise_closed or max_to <= hand["current_bet"]),
    }


def apply_action(state: dict[str, Any], user_id: int, action: str, amount: int | None = None) -> None:
    if state["status"] != "playing" or not state.get("hand"):
        raise ValueError("no active hand")
    p = _find_player(state, user_id)
    hand = state["hand"]
    if hand["action_seat"] != p["seat"] or not _can_act(p):
        raise ValueError("not your turn")

    action = action.lower()
    old_seat = p["seat"]
    call_amount = max(0, hand["current_bet"] - p["round_bet"])

    if action == "fold":
        p["folded"] = True
        hand["acted"].append(user_id)
        hand["log"].append(f"{p['name']} folds")
    elif action == "check":
        if call_amount != 0:
            raise ValueError("cannot check facing a bet")
        hand["acted"].append(user_id)
        hand["log"].append(f"{p['name']} checks")
    elif action == "call":
        if call_amount <= 0:
            raise ValueError("nothing to call")
        paid = _take_from_stack(p, call_amount)
        hand["acted"].append(user_id)
        hand["log"].append(f"{p['name']} calls {bb_text(state, paid)}")
    elif action in ("raise", "allin"):
        target = p["round_bet"] + p["stack"] if action == "allin" else int(amount or 0)
        max_to = p["round_bet"] + p["stack"]
        if target > max_to or target <= p["round_bet"]:
            raise ValueError("invalid raise amount")
        if target <= hand["current_bet"]:
            if target != max_to:
                raise ValueError("raise must exceed current bet")
            paid = _take_from_stack(p, target - p["round_bet"])
            hand["acted"].append(user_id)
            hand["log"].append(f"{p['name']} is all-in for {bb_text(state, p['round_bet'])}")
        else:
            if user_id in hand.get("raise_closed_for", []):
                raise ValueError("betting was not reopened by the short all-in")
            raise_size = target - hand["current_bet"]
            full_raise = raise_size >= hand["min_raise"]
            if not full_raise and target != max_to:
                raise ValueError(f"minimum raise-to is {hand['current_bet'] + hand['min_raise']}")
            _take_from_stack(p, target - p["round_bet"])
            previous = hand["current_bet"]
            hand["current_bet"] = target
            if full_raise:
                hand["min_raise"] = target - previous
                hand["acted"] = [user_id]
                hand["raise_closed_for"] = []
            else:
                prior_acted = list(hand["acted"])
                if user_id not in hand["acted"]:
                    hand["acted"].append(user_id)
                closed = set(hand.get("raise_closed_for", []))
                closed.update(uid for uid in prior_acted if uid != user_id)
                hand["raise_closed_for"] = list(closed)
            hand["log"].append(f"{p['name']} {'raises to' if action == 'raise' else 'is all-in to'} {bb_text(state, target)}")
    else:
        raise ValueError("unknown action")

    live = _in_hand_players(state)
    if len(live) == 1:
        _award_uncontested(state, live[0])
        return

    if _round_complete(state):
        _advance_round(state)
        _auto_progress_if_needed(state)
    else:
        _set_next_action(state, old_seat)
        _auto_progress_if_needed(state)


def _rake_amount(state: dict[str, Any], pot_amount: int) -> int:
    """10% rake capped at 5bb by default, rounded down to the smallest chip unit."""
    pct = float(state.get("rake_percent", 0.10))
    cap = int(state.get("rake_cap", int(state.get("big_blind", 1)) * 5))
    return max(0, min(int(int(pot_amount) * pct), cap, int(pot_amount)))


def _allocate_rake(pot_amounts: list[int], total_rake: int) -> list[int]:
    """Allocate hand rake proportionally across main/side pots without losing chips."""
    total = sum(int(x) for x in pot_amounts)
    if total <= 0 or total_rake <= 0:
        return [0 for _ in pot_amounts]
    raw = [total_rake * int(a) / total for a in pot_amounts]
    alloc = [int(x) for x in raw]
    remainder = total_rake - sum(alloc)
    order = sorted(range(len(raw)), key=lambda i: (raw[i] - alloc[i], pot_amounts[i]), reverse=True)
    for i in order[:remainder]:
        alloc[i] += 1
    return alloc


def _attach_net_results(state: dict[str, Any]) -> None:
    hand = state.get("hand") or {}
    starts = hand.get("starting_stacks") or {}
    results = []
    for p in state.get("seats", []):
        key = str(p.get("user_id"))
        if key not in starts:
            continue
        delta = int(p.get("stack", 0)) - int(starts[key])
        results.append({
            "user_id": p["user_id"],
            "name": p["name"],
            "amount": delta,
            "bb": delta / max(1, int(state.get("big_blind", 1))),
        })
    if state.get("last_result") is not None:
        state["last_result"]["net_results"] = results


def _award_uncontested(state: dict[str, Any], winner: dict[str, Any]) -> None:
    total = sum(int(p.get("contributed", 0)) for p in state["seats"])
    rake = _rake_amount(state, total)
    award = total - rake
    winner["stack"] += award
    state["last_result"] = {
        "type": "uncontested",
        "winners": [{"user_id": winner["user_id"], "name": winner["name"], "amount": award}],
        "board": list(state["hand"]["board"]),
        "gross_pot": total,
        "rake": rake,
        "message": f"{winner['name']} wins {bb_text(state, award)} · rake {bb_text(state, rake)}",
    }
    state["hand"]["revealed_user_ids"] = []
    _attach_net_results(state)
    _finish_hand(state)


def _build_side_pots(state: dict[str, Any]) -> list[dict[str, Any]]:
    contributors = [p for p in state["seats"] if p.get("contributed", 0) > 0]
    levels = sorted(set(int(p["contributed"]) for p in contributors))
    pots = []
    prev = 0
    for level in levels:
        involved = [p for p in contributors if p["contributed"] >= level]
        amount = (level - prev) * len(involved)
        eligible = [p for p in involved if p.get("in_hand") and not p.get("folded")]
        if amount > 0:
            pots.append({"amount": amount, "eligible": eligible})
        prev = level
    return pots


def _showdown(state: dict[str, Any]) -> None:
    hand = state["hand"]
    board = list(hand["board"])
    while len(board) < 5:
        # run out safely if called directly before river
        if len(board) == 0:
            hand["deck"].pop(); board.extend([hand["deck"].pop(), hand["deck"].pop(), hand["deck"].pop()])
        else:
            hand["deck"].pop(); board.append(hand["deck"].pop())
    hand["board"] = board

    live_players = _in_hand_players(state)
    scores = {p["user_id"]: rank_seven(p["cards"] + board) for p in live_players}
    hand["revealed_user_ids"] = [p["user_id"] for p in live_players]

    pots = _build_side_pots(state)
    gross_total = sum(int(p["amount"]) for p in pots)
    total_rake = _rake_amount(state, gross_total)
    rake_alloc = _allocate_rake([int(p["amount"]) for p in pots], total_rake)

    awards: dict[int, int] = {}
    pot_results = []
    for pot, pot_rake in zip(pots, rake_alloc):
        elig = pot["eligible"]
        if not elig:
            continue
        best = max(scores[p["user_id"]] for p in elig)
        winners = [p for p in elig if scores[p["user_id"]] == best]
        net_amount = max(0, int(pot["amount"]) - int(pot_rake))
        share, rem = divmod(net_amount, len(winners))
        # Odd chips are awarded clockwise from the button among tied winners.
        winners = sorted(winners, key=lambda p: ((p["seat"] - state["button_seat"]) % state["max_seats"]))
        for i, p in enumerate(winners):
            amt = share + (1 if i < rem else 0)
            p["stack"] += amt
            awards[p["user_id"]] = awards.get(p["user_id"], 0) + amt
        pot_results.append({
            "gross_amount": int(pot["amount"]),
            "amount": net_amount,
            "rake": int(pot_rake),
            "winners": [{"user_id": p["user_id"], "name": p["name"]} for p in winners],
            "hand": hand_name(best),
        })

    winners_payload = []
    for p in state["seats"]:
        if p["user_id"] in awards:
            winners_payload.append({
                "user_id": p["user_id"],
                "name": p["name"],
                "amount": awards[p["user_id"]],
                "hand": hand_name(scores[p["user_id"]]),
                "cards": list(p["cards"]),
            })
    msg = ", ".join(f"{w['name']} +{bb_text(state, w['amount'])} ({w['hand']})" for w in winners_payload)
    hand["showdown"] = {
        "scores": {str(uid): list(score) for uid, score in scores.items()},
        "pots": pot_results,
    }
    state["last_result"] = {
        "type": "showdown",
        "winners": winners_payload,
        "board": board,
        "gross_pot": gross_total,
        "rake": total_rake,
        "message": (msg or "Showdown complete") + f" · rake {bb_text(state, total_rake)}",
    }
    _attach_net_results(state)
    _finish_hand(state)


def _finish_hand(state: dict[str, Any]) -> None:
    hand = state.get("hand")
    if hand:
        hand["phase"] = "complete"
        hand["action_seat"] = None
    for p in state["seats"]:
        p["in_hand"] = False
        p["folded"] = False
        p["all_in"] = False
        p["round_bet"] = 0
        p["contributed"] = 0
    state["status"] = "waiting"


def public_state(state: dict[str, Any], viewer_id: int | None = None) -> dict[str, Any]:
    out = {
        k: v for k, v in state.items() if k not in ("seats", "hand")
    }
    revealed = set((state.get("hand") or {}).get("revealed_user_ids", []))
    out["seats"] = []
    for p in state["seats"]:
        item = {k: v for k, v in p.items() if k != "cards"}
        item["busted"] = int(p.get("stack", 0)) <= 0 and state.get("status") != "playing"
        if p["user_id"] == viewer_id or p["user_id"] in revealed:
            item["cards"] = list(p.get("cards", []))
        elif p.get("in_hand"):
            item["cards"] = ["??", "??"]
        else:
            item["cards"] = []
        out["seats"].append(item)
    if state.get("hand"):
        h = {k: v for k, v in state["hand"].items() if k != "deck"}
        h["acted"] = list(h.get("acted", []))
        out["hand"] = h
    else:
        out["hand"] = None
    if viewer_id is not None:
        try:
            out["legal"] = legal_actions(state, viewer_id)
        except ValueError:
            out["legal"] = {"can_act": False}
    return out


# v1.14 continuous-table lifecycle. Wrappers preserve the verified v1.4
# betting/rake/showdown implementation while adding ready/sit-out semantics.
import time as _jj_time

_jj_original_seat_player = seat_player
_jj_original_start_hand = start_hand
_jj_original_finish_hand = _finish_hand


def _jj_player_defaults(player: dict[str, Any]) -> None:
    player.setdefault("ready", False)
    player.setdefault("sitting_out", False)
    player.setdefault("sit_out_next", False)


def _jj_next_hand_players(state: dict[str, Any]) -> list[dict[str, Any]]:
    for player in state.get("seats", []):
        _jj_player_defaults(player)
    return [
        player for player in state.get("seats", [])
        if int(player.get("stack", 0)) > 0 and not bool(player.get("sitting_out"))
    ]


def seat_player(state: dict[str, Any], *args, **kwargs) -> None:
    _jj_original_seat_player(state, *args, **kwargs)
    user_id = kwargs.get("user_id")
    for player in state.get("seats", []):
        if user_id is None or int(player.get("user_id", -1)) == int(user_id):
            _jj_player_defaults(player)
            player["ready"] = False
            player["sitting_out"] = False
            player["sit_out_next"] = False
    state.setdefault("session_active", False)
    state.setdefault("next_hand_at_epoch", None)


def start_hand(state: dict[str, Any]) -> None:
    """Start a hand while excluding players who explicitly sit out."""
    active = _jj_next_hand_players(state)
    if len(active) < 2:
        raise ValueError("at least two active players with chips are required")
    held_stacks: list[tuple[dict[str, Any], int]] = []
    for player in state.get("seats", []):
        if player.get("sitting_out") and int(player.get("stack", 0)) > 0:
            held_stacks.append((player, int(player["stack"])))
            player["stack"] = 0
    state["next_hand_at_epoch"] = None
    # The previous result is shown only during the inter-hand pause. Clear it
    # before the next deal so an old winner banner can never overlap a new hand.
    state["last_result"] = None
    try:
        _jj_original_start_hand(state)
    finally:
        for player, stack in held_stacks:
            player["stack"] = stack
    for player in state.get("seats", []):
        _jj_player_defaults(player)
        player["ready"] = False


def _finish_hand(state: dict[str, Any]) -> None:
    """Finish normally, then apply next-hand sit-out reservations and queue the next deal."""
    _jj_original_finish_hand(state)
    for player in state.get("seats", []):
        _jj_player_defaults(player)
        if player.get("sit_out_next"):
            player["sitting_out"] = True
            player["sit_out_next"] = False
            player["ready"] = False
    active = _jj_next_hand_players(state)
    if bool(state.get("session_active")) and len(active) >= 2:
        state["next_hand_at_epoch"] = _jj_time.time() + 2.4
    else:
        state["next_hand_at_epoch"] = None
        if len(active) < 2:
            state["session_active"] = False
            for player in state.get("seats", []):
                player["ready"] = False


# v1.16 join-during-hand lifecycle.
# A new player may reserve an empty seat while a hand is running, but is never
# inserted into that hand. They enter SIT OUT and explicitly opt into a future
# hand with the return/presence action. Existing waiting-state seating keeps the
# verified engine path unchanged.
_jj_v16_previous_seat_player = seat_player


def seat_player(state: dict[str, Any], *, user_id: int, name: str, seat: int, stack: int) -> None:
    if state.get("status") != "playing":
        _jj_v16_previous_seat_player(state, user_id=user_id, name=name, seat=seat, stack=stack)
        return
    if not 0 <= int(seat) < int(state.get("max_seats", 6)):
        raise ValueError("invalid seat")
    if any(int(p.get("seat", -1)) == int(seat) for p in state.get("seats", [])):
        raise ValueError("seat is occupied")
    if any(int(p.get("user_id", -1)) == int(user_id) for p in state.get("seats", [])):
        raise ValueError("already seated")
    if not int(state.get("min_buyin", stack)) <= int(stack) <= int(state.get("max_buyin", stack)):
        raise ValueError("buy-in is outside table limits")
    state.setdefault("session_active", True)
    state.setdefault("next_hand_at_epoch", None)
    state["seats"].append({
        "user_id": int(user_id), "name": name, "seat": int(seat), "stack": int(stack),
        "in_hand": False, "folded": False, "all_in": False, "round_bet": 0,
        "contributed": 0, "cards": [], "ready": False,
        "sitting_out": True, "sit_out_next": False,
    })
    state["seats"].sort(key=lambda player: int(player.get("seat", 0)))

# v1.20.0 completed-hand card privacy
# Never reveal a mucked/folded opponent hand just because the hand reached the
# complete state. The viewer always sees their own cards; other players' cards
# are disclosed only when that player actually reached showdown.
_jj_v120_public_state_before_privacy = public_state


def public_state(state: dict[str, Any], viewer_id: int | None = None) -> dict[str, Any]:
    out = _jj_v120_public_state_before_privacy(state, viewer_id)
    hand = state.get("hand") or {}
    scores = ((hand.get("showdown") or {}).get("scores") or {})
    showdown_ids: set[int] = set()
    for raw_uid in scores.keys():
        try:
            showdown_ids.add(int(raw_uid))
        except (TypeError, ValueError):
            continue

    private_by_uid = {}
    for player in state.get("seats", []):
        try:
            uid = int(player.get("user_id"))
        except (TypeError, ValueError):
            continue
        private_by_uid[uid] = player

    for item in out.get("seats", []):
        try:
            uid = int(item.get("user_id"))
        except (TypeError, ValueError):
            item["cards"] = []
            continue
        private = private_by_uid.get(uid) or {}
        if viewer_id is not None and uid == int(viewer_id):
            item["cards"] = list(private.get("cards") or [])
        elif uid in showdown_ids:
            item["cards"] = list(private.get("cards") or [])
        elif bool(private.get("in_hand")):
            item["cards"] = ["??", "??"] if private.get("cards") else []
        else:
            item["cards"] = []
    return out



# v1.21.0 private action receipt filter.
# Keep idempotency receipts in persisted server state, never in client-visible state.
_jj_v121_public_state = public_state
def public_state(*args, **kwargs):
    out = _jj_v121_public_state(*args, **kwargs)
    if isinstance(out, dict):
        out.pop("_processed_action_ids", None)
    return out

# Compatibility anchor consumed by v49_patch; the actual filter is the wrapper above.
# out = {k: v for k, v in state.items() if k not in ("seats", "hand", "_processed_action_ids")};


# v1.23.0 mobile poker second-pass engine UX.
# Keep the established poker rules and card-privacy layer, but fix three pieces
# of table pacing that are directly visible to players: no-flop-no-drop,
# staged forced all-in runouts, and a longer synchronized showdown hold.
JJ_V123_RUNOUT_STREET_DELAY = 1.15
JJ_V123_SHOWDOWN_REVEAL_DELAY = 1.35
JJ_V123_SHOWDOWN_HOLD_SECONDS = 7.5


def _jj_v123_no_decision(state: dict) -> bool:
    """True only when nobody has a meaningful betting decision left."""
    if state.get("status") != "playing" or len(_in_hand_players(state)) <= 1:
        return False
    actors = list(_can_act(state))
    if not actors:
        return True
    if len(actors) > 1:
        return False
    actor = actors[0]
    hand = state.get("hand") or {}
    current = int(hand.get("current_bet", 0) or 0)
    paid = int(actor.get("round_bet", 0) or 0)
    return paid >= current


def _jj_v123_queue_runout(state: dict, delay: float = JJ_V123_RUNOUT_STREET_DELAY) -> None:
    hand = state.get("hand") or {}
    if not hand:
        return
    hand["forced_runout"] = True
    hand["runout_due_at_epoch"] = time.time() + max(0.15, float(delay))
    hand["action_seat"] = None
    hand.pop("action_deadline", None)


def _jj_v123_prepare_runout(state: dict) -> None:
    hand = state.get("hand") or {}
    if not hand:
        return
    _consume_bets_into_pot(state)
    hand["current_bet"] = 0
    hand["min_raise"] = int(state.get("big_blind", 100) or 100)
    hand["raises_in_round"] = 0
    hand["acted"] = []
    for player in _occupied(state):
        player["round_bet"] = 0
    _jj_v123_queue_runout(state)


_jj_v123_base_award_uncontested = _award_uncontested


def _award_uncontested(state: dict) -> None:
    """Use No Flop, No Drop for pots that end before any community card."""
    hand = state.get("hand")
    alive = _in_hand_players(state)
    if not hand or len(alive) != 1:
        return _jj_v123_base_award_uncontested(state)
    if len(hand.get("board") or []) != 0:
        return _jj_v123_base_award_uncontested(state)

    winner = alive[0]
    pot = sum(int(player.get("contributed", 0) or 0) for player in _occupied(state))
    hand["rake"] = 0
    winner["stack"] = int(winner.get("stack", 0) or 0) + max(0, int(pot))
    for player in _occupied(state):
        player["contributed"] = 0
        player["round_bet"] = 0
    _finish_hand(state, winner.get("name") or "")


_jj_v123_base_advance_round = _advance_round


def _advance_round(state: dict) -> None:
    hand = state.get("hand") or {}
    if (
        state.get("status") == "playing"
        and len(hand.get("board") or []) < 5
        and _jj_v123_no_decision(state)
    ):
        _jj_v123_prepare_runout(state)
        return
    _jj_v123_base_advance_round(state)


_jj_v123_base_auto_progress = _auto_progress_if_needed


def _auto_progress_if_needed(state: dict) -> None:
    if state.get("status") != "playing":
        return
    alive = _in_hand_players(state)
    if len(alive) == 1:
        _award_uncontested(state)
        return
    actors = list(_can_act(state))
    if len(actors) <= 1:
        if _jj_v123_no_decision(state):
            hand = state.get("hand") or {}
            if not hand.get("forced_runout"):
                if len(hand.get("board") or []) < 5:
                    _jj_v123_prepare_runout(state)
                else:
                    _jj_v123_queue_runout(state, JJ_V123_SHOWDOWN_REVEAL_DELAY)
        # Never delegate the <=1-player branch to the legacy while-loop: that
        # loop is exactly what used to expose flop/turn/river in one frame.
        return
    _jj_v123_base_auto_progress(state)


def advance_forced_runout(state: dict) -> bool:
    """Advance exactly one visual runout stage when its server timer expires."""
    if state.get("status") != "playing":
        return False
    hand = state.get("hand") or {}
    if not hand.get("forced_runout"):
        return False
    due = float(hand.get("runout_due_at_epoch") or 0)
    if due > time.time():
        return False
    if len(_in_hand_players(state)) <= 1:
        hand.pop("forced_runout", None)
        hand.pop("runout_due_at_epoch", None)
        _award_uncontested(state)
        return True

    hand.pop("runout_due_at_epoch", None)
    if len(hand.get("board") or []) < 5:
        _deal_next_street(state)
        hand = state.get("hand") or hand
        hand["action_seat"] = None
        hand.pop("action_deadline", None)
        if len(hand.get("board") or []) < 5:
            _jj_v123_queue_runout(state, JJ_V123_RUNOUT_STREET_DELAY)
        else:
            _jj_v123_queue_runout(state, JJ_V123_SHOWDOWN_REVEAL_DELAY)
        return True

    hand.pop("forced_runout", None)
    hand.pop("runout_due_at_epoch", None)
    _showdown(state)
    return True


_jj_v123_base_finish_hand = _finish_hand


def _finish_hand(state: dict, winner_name: str) -> None:
    hand_before = state.get("hand") or {}
    had_showdown = bool(hand_before.get("showdown"))
    _jj_v123_base_finish_hand(state, winner_name)
    result = state.get("last_result") or {}
    is_showdown = had_showdown or result.get("type") == "showdown" or bool(result.get("showdown"))
    if is_showdown:
        hold_until = time.time() + JJ_V123_SHOWDOWN_HOLD_SECONDS
        state["showdown_hold_until_epoch"] = hold_until
        state["next_hand_at_epoch"] = max(float(state.get("next_hand_at_epoch") or 0), hold_until)


_jj_v123_base_start_hand = start_hand


def start_hand(state: dict, *args, **kwargs):
    hold = float(state.get("showdown_hold_until_epoch") or 0)
    if hold > time.time():
        return None
    state.pop("showdown_hold_until_epoch", None)
    return _jj_v123_base_start_hand(state, *args, **kwargs)


_jj_v123_base_legal_actions = legal_actions


def legal_actions(state: dict, user_id: int) -> dict:
    legal = dict(_jj_v123_base_legal_actions(state, user_id) or {})
    hand = state.get("hand") or {}
    reasons: dict[str, str] = {}
    status_reason = ""

    hero = next((p for p in _occupied(state) if int(p.get("user_id") or -1) == int(user_id)), None)
    actor = next((p for p in _occupied(state) if p.get("seat") == hand.get("action_seat")), None)
    if hand.get("forced_runout"):
        status_reason = "オールイン後のボードを順番に公開しています"
    elif float(state.get("showdown_hold_until_epoch") or 0) > time.time():
        status_reason = "ショーダウンのカードを確認する時間です"
    elif not hero:
        status_reason = "着席するとアクションできます"
    elif state.get("status") != "playing":
        status_reason = "次のハンドを待っています"
    elif hero.get("folded"):
        status_reason = "このハンドではフォールド済みです"
    elif hero.get("all_in"):
        status_reason = "オールイン済みです"
    elif not legal.get("can_act"):
        status_reason = f"{actor.get('name')}さんの番です" if actor else "他のプレイヤーのアクション待ちです"
    else:
        status_reason = "あなたの番です"

    if not legal.get("can_check"):
        reasons["check"] = "相手のベットに対応する必要があります"
    if not legal.get("can_call"):
        reasons["call"] = "コールする額はありません"
    if not legal.get("can_raise"):
        if legal.get("raise_locked_allin"):
            reasons["raise"] = "ショートオールインでは再レイズ権が開いていません"
        else:
            reasons["raise"] = "現在はベット／レイズできません"
    if not legal.get("can_all_in"):
        reasons["allin"] = "現在はオールインできません"
    if legal.get("can_check"):
        reasons["fold"] = "チェックで無料に続行できるため、誤操作防止で非表示にしています"

    legal["status_reason"] = status_reason
    legal["disabled_reasons"] = reasons
    legal["runout_active"] = bool(hand.get("forced_runout"))
    return legal

# v1.23.0 occupied-seat compatibility.
# The reconstructed production engine represents occupied seats directly in the
# table state's `seats` list. v1.23's final wrappers use one small accessor so
# every seat traversal is safe even though older runtimes never exposed a helper
# named `_occupied`.
def _occupied(state: dict) -> list[dict]:
    return list(state.get("seats") or [])

# v1.23.0 reconstructed-engine compatibility final.
# v1.23 is layered onto the verified production engine rather than replacing it.
# The established engine stores cumulative pot contributions on each seat,
# `_can_act` accepts one player, `_advance_round` deals exactly one street, and
# `_finish_hand` accepts the state only. These final wrappers intentionally adapt
# v1.23 to those contracts so staging never depends on invented helper APIs.
import inspect
import time


def _occupied(state: dict) -> list[dict]:
    return list(state.get("seats") or [])


def _jj_v123_actionable(state: dict) -> list[dict]:
    return [player for player in _in_hand_players(state) if _can_act(player)]


def _jj_v123_no_decision(state: dict) -> bool:
    if state.get("status") != "playing" or len(_in_hand_players(state)) <= 1:
        return False
    actors = _jj_v123_actionable(state)
    if not actors:
        return True
    if len(actors) > 1:
        return False
    actor = actors[0]
    hand = state.get("hand") or {}
    current = int(hand.get("current_bet", 0) or 0)
    paid = int(actor.get("round_bet", 0) or 0)
    return paid >= current


def _jj_v123_prepare_runout(state: dict) -> None:
    """Freeze betting while preserving cumulative contributions for settlement."""
    hand = state.get("hand") or {}
    if not hand:
        return
    # `contributed` is already the authoritative cumulative pot in the verified
    # engine. Reset only the street-facing amounts; showdown/side-pot code will
    # consume the cumulative contributions later.
    for player in _occupied(state):
        player["round_bet"] = 0
    hand["current_bet"] = 0
    hand["min_raise"] = int(state.get("big_blind", 100) or 100)
    hand["raises_in_round"] = 0
    hand["acted"] = []
    hand["raise_closed_for"] = []
    _jj_v123_queue_runout(state)


def _jj_v123_call_base_award(state: dict, winner: dict | None = None):
    """Delegate postflop settlement without assuming a historical wrapper signature."""
    fn = _jj_v123_base_award_uncontested
    params = [
        p for p in inspect.signature(fn).parameters.values()
        if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    if len(params) >= 2:
        return fn(state, winner or (_in_hand_players(state)[0] if _in_hand_players(state) else None))
    return fn(state)


def _award_uncontested(state: dict) -> None:
    """No Flop, No Drop while preserving the normal winner/result payload."""
    hand = state.get("hand")
    alive = _in_hand_players(state)
    if not hand or len(alive) != 1:
        return _jj_v123_call_base_award(state, alive[0] if alive else None)
    if len(hand.get("board") or []) != 0:
        return _jj_v123_call_base_award(state, alive[0])

    winner = alive[0]
    pot = sum(int(player.get("contributed", 0) or 0) for player in _occupied(state))
    hand["rake"] = 0
    winner["stack"] = int(winner.get("stack", 0) or 0) + max(0, int(pot))
    state["last_result"] = {
        "type": "uncontested",
        "winners": [{
            "user_id": winner.get("user_id"),
            "name": winner.get("name") or "",
            "amount": int(pot),
        }],
        "board": list(hand.get("board") or []),
        "message": f"{winner.get('name') or ''} wins {bb_text(state, pot)}",
    }
    for player in _occupied(state):
        player["contributed"] = 0
        player["round_bet"] = 0
    _finish_hand(state, winner.get("name") or "")


def _auto_progress_if_needed(state: dict) -> None:
    """Preserve normal betting; intercept only the forced no-decision runout."""
    if state.get("status") != "playing":
        return
    alive = _in_hand_players(state)
    if len(alive) == 1:
        _award_uncontested(state)
        return
    actors = _jj_v123_actionable(state)
    if len(actors) <= 1:
        if _jj_v123_no_decision(state):
            hand = state.get("hand") or {}
            if not hand.get("forced_runout"):
                if len(hand.get("board") or []) < 5:
                    _jj_v123_prepare_runout(state)
                else:
                    _jj_v123_queue_runout(state, JJ_V123_SHOWDOWN_REVEAL_DELAY)
        return
    _jj_v123_base_auto_progress(state)


def advance_forced_runout(state: dict) -> bool:
    """Advance one visible stage using the established one-street dealer."""
    if state.get("status") != "playing":
        return False
    hand = state.get("hand") or {}
    if not hand.get("forced_runout"):
        return False
    due = float(hand.get("runout_due_at_epoch") or 0)
    if due > time.time():
        return False
    if len(_in_hand_players(state)) <= 1:
        hand.pop("forced_runout", None)
        hand.pop("runout_due_at_epoch", None)
        _award_uncontested(state)
        return True

    hand.pop("runout_due_at_epoch", None)
    if len(hand.get("board") or []) < 5:
        # Captured before v1.23 replaced `_advance_round`; this is the verified
        # production dealer and advances exactly preflop->flop, flop->turn, or
        # turn->river while preserving deck burn behavior.
        _jj_v123_base_advance_round(state)
        hand = state.get("hand") or hand
        hand["action_seat"] = None
        hand.pop("action_deadline", None)
        if len(hand.get("board") or []) < 5:
            _jj_v123_queue_runout(state, JJ_V123_RUNOUT_STREET_DELAY)
        else:
            _jj_v123_queue_runout(state, JJ_V123_SHOWDOWN_REVEAL_DELAY)
        return True

    hand.pop("forced_runout", None)
    hand.pop("runout_due_at_epoch", None)
    _showdown(state)
    return True


def _finish_hand(state: dict, winner_name: str | None = None) -> None:
    """Keep the established one-argument finish contract and add showdown hold."""
    hand_before = state.get("hand") or {}
    had_showdown = bool(hand_before.get("showdown"))
    _jj_v123_base_finish_hand(state)
    result = state.get("last_result") or {}
    is_showdown = had_showdown or result.get("type") == "showdown" or bool(result.get("showdown"))
    if is_showdown:
        hold_until = time.time() + JJ_V123_SHOWDOWN_HOLD_SECONDS
        state["showdown_hold_until_epoch"] = hold_until
        state["next_hand_at_epoch"] = max(float(state.get("next_hand_at_epoch") or 0), hold_until)

# v1.23.0 uncontested award call-signature compatibility.
# The reconstructed engine's apply_action() calls _award_uncontested(state,
# winner), while v1.23's final no-flop-no-drop wrapper also calls it internally
# with state only. Keep both historical contracts valid without duplicating the
# settlement logic.
_jj_v123_one_arg_award_uncontested = _award_uncontested


def _award_uncontested(state: dict, winner: dict | None = None) -> None:
    return _jj_v123_one_arg_award_uncontested(state)

