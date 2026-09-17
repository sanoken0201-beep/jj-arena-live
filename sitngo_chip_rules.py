"""Tournament-only chip denomination, color-up, and odd-chip rules.

The immutable materialized poker engine remains untouched. Sit&Go receives an
isolated engine instance, so these rules apply only to tournament tables:

* 100 is the absolute minimum denomination;
* scheduled color-ups happen only between hands;
* color-ups preserve the tournament chip total and never bust a live player;
* normal raises must use the current denomination;
* split pots never create sub-denomination chips;
* odd chips are awarded from the first seat left of the button;
* the big-blind ante is dead money in the main pot, not a second logical pot.
"""
from __future__ import annotations

from math import gcd
from typing import Any


MIN_CHIP = 100
STANDARD_DENOMINATIONS = (
    100,
    500,
    1_000,
    5_000,
    10_000,
    25_000,
    50_000,
    100_000,
    500_000,
    1_000_000,
    5_000_000,
    10_000_000,
    25_000_000,
    50_000_000,
    100_000_000,
)


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _starting_stack(state: dict[str, Any]) -> int:
    tournament = state.get("tournament") or {}
    explicit = _int(tournament.get("starting_stack"))
    if explicit > 0:
        return explicit
    entrants = max(1, _int(tournament.get("entrants"), 1))
    total = _int(tournament.get("total_chips"))
    if total > 0 and total % entrants == 0:
        return total // entrants
    return max(MIN_CHIP, max((_int(p.get("stack")) for p in state.get("seats", [])), default=MIN_CHIP))


def chip_unit_for_level(state: dict[str, Any], level_index: int | None = None) -> int:
    """Return the largest conventional denomination safe for all remaining levels.

    Including the starting stack in the GCD guarantees that the whole tournament
    chip supply is divisible by every selected denomination for any entrant count.
    Remaining forced bets are included so a future SB/BB/BBA can always be posted
    exactly after lower chips have been removed.
    """
    tournament = state.get("tournament") or {}
    levels = list(tournament.get("structure") or [])
    if not levels:
        return MIN_CHIP
    if level_index is None:
        level_index = max(0, _int(tournament.get("level"), 1) - 1)
    level_index = max(0, min(int(level_index), len(levels) - 1))

    common = abs(_starting_stack(state))
    for level in levels[level_index:]:
        for key in ("small_blind", "big_blind", "bb_ante"):
            amount = abs(_int(level.get(key)))
            if amount:
                common = gcd(common, amount)

    candidates = [d for d in STANDARD_DENOMINATIONS if d <= common and common % d == 0]
    return max(candidates or [MIN_CHIP])


def _left_of_button_order(state: dict[str, Any], players: list[dict[str, Any]]) -> list[dict[str, Any]]:
    max_seats = max(2, _int(state.get("max_seats"), 6))
    button = _int(state.get("button_seat"), -1)
    return sorted(players, key=lambda p: ((_int(p.get("seat")) - button - 1) % max_seats, _int(p.get("seat"))))


def color_up(state: dict[str, Any], new_unit: int | None = None) -> list[dict[str, int]]:
    """Convert every live stack to ``new_unit`` exactly between hands.

    This online color-up uses deterministic bounded apportionment rather than
    inventing fractional chips. The total chip supply is unchanged, and every
    player who had chips before the color-up keeps at least one chip afterward.
    """
    if state.get("status") == "playing":
        raise RuntimeError("Sit&Go color-up attempted during an active hand")
    if any(_int(p.get("contributed")) or _int(p.get("round_bet")) for p in state.get("seats", [])):
        raise RuntimeError("Sit&Go color-up attempted with chips still in the pot")
    if _int(state.get("_ante_paid")):
        raise RuntimeError("Sit&Go color-up attempted with an ante still in the pot")

    target = max(MIN_CHIP, _int(new_unit, chip_unit_for_level(state)))
    old_unit = max(MIN_CHIP, _int(state.get("chip_unit"), MIN_CHIP))
    if target < old_unit:
        raise RuntimeError("Sit&Go denomination progression is invalid")
    if target == old_unit:
        state["chip_unit"] = target
        return []

    seats = list(state.get("seats") or [])
    original = {_int(p.get("user_id")): _int(p.get("stack")) for p in seats}
    total = sum(original.values())
    if total % target:
        raise RuntimeError("Sit&Go chip supply cannot be colored up exactly")

    live = [p for p in seats if _int(p.get("stack")) > 0]
    total_units = total // target
    if total_units < len(live):
        raise RuntimeError("Sit&Go color-up would eliminate a live player")

    ordered = _left_of_button_order(state, live)
    tie_rank = {_int(p.get("user_id")): index for index, p in enumerate(ordered)}
    quota = {_int(p.get("user_id")): original[_int(p.get("user_id"))] / target for p in live}
    allocation = {
        _int(p.get("user_id")): max(1, original[_int(p.get("user_id"))] // target)
        for p in live
    }

    used = sum(allocation.values())
    while used > total_units:
        candidates = [p for p in live if allocation[_int(p.get("user_id"))] > 1]
        if not candidates:
            raise RuntimeError("Sit&Go color-up cannot preserve all live players")
        chosen = min(
            candidates,
            key=lambda p: (
                quota[_int(p.get("user_id"))] - allocation[_int(p.get("user_id"))],
                tie_rank[_int(p.get("user_id"))],
            ),
        )
        allocation[_int(chosen.get("user_id"))] -= 1
        used -= 1

    while used < total_units:
        chosen = max(
            live,
            key=lambda p: (
                quota[_int(p.get("user_id"))] - allocation[_int(p.get("user_id"))],
                -tie_rank[_int(p.get("user_id"))],
            ),
        )
        allocation[_int(chosen.get("user_id"))] += 1
        used += 1

    adjustments: list[dict[str, int]] = []
    for player in seats:
        uid = _int(player.get("user_id"))
        before = original[uid]
        after = allocation.get(uid, 0) * target
        player["stack"] = after
        if before != after:
            adjustments.append({"user_id": uid, "before": before, "after": after, "delta": after - before})

    if sum(_int(p.get("stack")) for p in seats) != total:
        raise RuntimeError("Sit&Go color-up changed the tournament chip total")
    if any(0 < original[_int(p.get("user_id"))] and _int(p.get("stack")) <= 0 for p in seats):
        raise RuntimeError("Sit&Go color-up eliminated a live player")
    if any(_int(p.get("stack")) % target for p in seats):
        raise RuntimeError("Sit&Go color-up left an obsolete denomination")

    state["chip_unit"] = target
    tournament = state.get("tournament") or {}
    tournament.setdefault("chip_up_history", []).append(
        {
            "level": _int(tournament.get("level"), 1),
            "from_unit": old_unit,
            "to_unit": target,
            "hand_no": _int(state.get("hand_no")),
            "adjustments": adjustments,
        }
    )
    return adjustments


def _merge_dead_ante_into_main_pot(engine, state: dict[str, Any], base_builder) -> list[dict[str, Any]]:
    """Fold the runtime's synthetic BBA pot into the actual main pot.

    The original tournament adapter represented BBA as a leading synthetic pot
    so it did not count as a call credit. That is useful for contribution logic,
    but showdown must treat the ante as dead money in the main pot; otherwise a
    tied hand can receive two independent odd-chip decisions.
    """
    pots = list(base_builder(state))
    ante = _int(state.get("_ante_paid"))
    if ante <= 0 or not pots:
        return pots
    first = pots[0]
    if _int(first.get("amount")) != ante:
        raise RuntimeError("Sit&Go BBA pot ordering invariant failed")
    if len(pots) == 1:
        return pots

    ante_pot = pots.pop(0)
    main = pots[0]
    main["amount"] = _int(main.get("amount")) + ante

    # Every non-folded player still in the hand is eligible for dead ante money.
    # Unioning eligibility is defensive for short-stack/legacy states while
    # preserving the canonical order of the actual main-pot participants.
    eligible = {_int(p.get("user_id")): p for p in main.get("eligible", [])}
    for player in ante_pot.get("eligible", []):
        eligible.setdefault(_int(player.get("user_id")), player)
    main["eligible"] = sorted(eligible.values(), key=lambda p: _int(p.get("seat")))
    return pots


def _reallocate_showdown(engine, state: dict[str, Any]) -> None:
    """Replace canonical 1-point split logic with denomination-sized odd chips."""
    unit = _int(state.get("chip_unit"))
    if unit < MIN_CHIP:
        # Legacy hand already in progress when this code was deployed. It will
        # be colored up before the next hand instead of mutating history mid-hand.
        return
    result = state.get("last_result") or {}
    hand = state.get("hand") or {}
    showdown = hand.get("showdown") or {}
    pots = list(showdown.get("pots") or [])
    if result.get("type") != "showdown" or not pots:
        return

    canonical_awards = {_int(w.get("user_id")): _int(w.get("amount")) for w in result.get("winners", [])}
    players = {_int(p.get("user_id")): p for p in state.get("seats", [])}
    for uid, amount in canonical_awards.items():
        if uid in players:
            players[uid]["stack"] -= amount

    aggregate: dict[int, int] = {}
    for pot in pots:
        amount = _int(pot.get("amount"))
        if amount % unit:
            raise RuntimeError("Sit&Go pot contains chips below the active denomination")
        winner_ids = [_int(w.get("user_id")) for w in pot.get("winners", []) if _int(w.get("user_id")) in players]
        if not winner_ids:
            continue
        ordered = _left_of_button_order(state, [players[uid] for uid in winner_ids])
        units, unit_remainder = divmod(amount, unit)
        if unit_remainder:
            raise RuntimeError("Sit&Go split pot produced a fractional chip")
        share_units, odd_units = divmod(units, len(ordered))
        awards = []
        for index, player in enumerate(ordered):
            uid = _int(player.get("user_id"))
            award = (share_units + (1 if index < odd_units else 0)) * unit
            player["stack"] += award
            aggregate[uid] = aggregate.get(uid, 0) + award
            awards.append({"user_id": uid, "name": player.get("name", ""), "amount": award})
        pot["winners"] = [{"user_id": x["user_id"], "name": x["name"]} for x in awards]
        pot["awards"] = awards

    templates = {_int(w.get("user_id")): dict(w) for w in result.get("winners", [])}
    winners_payload = []
    for player in state.get("seats", []):
        uid = _int(player.get("user_id"))
        if uid not in aggregate:
            continue
        payload = templates.get(uid, {"user_id": uid, "name": player.get("name", "")})
        payload["amount"] = aggregate[uid]
        winners_payload.append(payload)
    result["winners"] = winners_payload
    result["message"] = ", ".join(
        f"{w.get('name','')} +{engine.bb_text(state, w['amount'])} ({w.get('hand','Showdown')})"
        for w in winners_payload
    ) + " · rake 0bb"
    engine._attach_net_results(state)


def validate_chip_integrity(state: dict[str, Any]) -> None:
    """Fail closed if a new tournament state ever creates an illegal chip value."""
    if "chip_unit" not in state:
        return
    unit = max(MIN_CHIP, _int(state.get("chip_unit"), MIN_CHIP))
    tournament = state.get("tournament") or {}
    values = [
        ("small blind", _int(state.get("small_blind"))),
        ("big blind", _int(state.get("big_blind"))),
        ("BBA", _int(tournament.get("bb_ante"))),
        ("posted ante", _int(state.get("_ante_paid"))),
    ]
    for player in state.get("seats", []):
        uid = _int(player.get("user_id"))
        values.extend(
            [
                (f"stack:{uid}", _int(player.get("stack"))),
                (f"round bet:{uid}", _int(player.get("round_bet"))),
                (f"contribution:{uid}", _int(player.get("contributed"))),
            ]
        )
    bad = [(label, amount) for label, amount in values if amount % unit]
    if bad:
        raise RuntimeError(f"Sit&Go denomination invariant failed: unit={unit}, bad={bad[:4]}")


def install(sitngo_runtime) -> None:
    """Install tournament-only guards without touching the canonical ring engine."""
    if getattr(sitngo_runtime, "_JJ_CHIP_RULES_INSTALLED", False):
        return

    original_make_engine = sitngo_runtime.make_engine
    runtime_cls = sitngo_runtime.TournamentRuntime
    original_save = runtime_cls.save
    original_public = runtime_cls.public

    def make_engine():
        engine = original_make_engine()
        original_start = engine.start_hand
        original_action = engine.apply_action
        original_showdown = engine._showdown
        original_side_pots = engine._build_side_pots

        def build_side_pots(state):
            if state.get("tournament"):
                return _merge_dead_ante_into_main_pot(engine, state, original_side_pots)
            return original_side_pots(state)

        def start_hand(state):
            if state.get("tournament"):
                target = chip_unit_for_level(state)
                if "chip_unit" not in state:
                    state["chip_unit"] = MIN_CHIP
                if target > _int(state.get("chip_unit"), MIN_CHIP):
                    color_up(state, target)
                else:
                    state["chip_unit"] = target
                validate_chip_integrity(state)
            return original_start(state)

        def apply_action(state, user_id, action, amount=None):
            if state.get("tournament") and "chip_unit" in state and str(action).lower() == "raise":
                unit = max(MIN_CHIP, _int(state.get("chip_unit"), MIN_CHIP))
                target = _int(amount)
                if target % unit:
                    raise ValueError(f"ベット・レイズ額は{unit:,}点単位で入力してください")
            value = original_action(state, user_id, action, amount)
            if state.get("tournament"):
                validate_chip_integrity(state)
            return value

        def showdown(state):
            value = original_showdown(state)
            if state.get("tournament"):
                _reallocate_showdown(engine, state)
                validate_chip_integrity(state)
            return value

        engine._build_side_pots = build_side_pots
        engine.start_hand = start_hand
        engine.apply_action = apply_action
        engine._showdown = showdown
        return engine

    def save(self, state, *args, **kwargs):
        validate_chip_integrity(state)
        return original_save(self, state, *args, **kwargs)

    def public(self, state, viewer=None):
        value = original_public(self, state, viewer)
        if state.get("tournament"):
            unit = max(MIN_CHIP, _int(state.get("chip_unit"), MIN_CHIP))
            value["chip_unit"] = unit
            value["tournament"]["chip_unit"] = unit
            if isinstance(value.get("legal"), dict):
                value["legal"]["chip_unit"] = unit
        return value

    sitngo_runtime.make_engine = make_engine
    runtime_cls.save = save
    runtime_cls.public = public
    sitngo_runtime._JJ_CHIP_RULES_INSTALLED = True


__all__ = [
    "MIN_CHIP",
    "STANDARD_DENOMINATIONS",
    "chip_unit_for_level",
    "color_up",
    "install",
    "validate_chip_integrity",
]
