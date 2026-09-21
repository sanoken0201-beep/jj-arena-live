from __future__ import annotations

"""Server-authoritative 30-second action clock with forced time-bank cards.

Every seated player receives three cards for the life of that seating/tournament.
Each normal turn gets 30 seconds. If the deadline expires, one remaining card is
consumed automatically and the same decision receives another 30 seconds. After
all three cards are gone, the next missed deadline is always a fold, even when a
check would otherwise be available.
"""

import asyncio
import time
from datetime import datetime, timezone

ACTION_SECONDS = 30
TIME_BANK_CARDS = 3
SITNGO_TIMEOUT_GRACE_SECONDS = 0.35
FORCED_FOLD_LOG_SUFFIX = "time bank exhausted · forced fold"


def _deadline_epoch(hand: dict) -> float | None:
    raw = hand.get("action_deadline")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw)).timestamp()
    except (TypeError, ValueError):
        return None


def _active_player(state: dict) -> dict | None:
    hand = state.get("hand") or {}
    seat = hand.get("action_seat")
    if seat is None:
        return None
    return next((player for player in state.get("seats", []) if player.get("seat") == seat), None)


def _ensure_cards(player: dict) -> int:
    if "timebank_cards" not in player:
        player["timebank_cards"] = TIME_BANK_CARDS
    cards = max(0, min(TIME_BANK_CARDS, int(player.get("timebank_cards") or 0)))
    player["timebank_cards"] = cards
    return cards


def _set_deadline(hand: dict, *, now_epoch: float, seconds: int = ACTION_SECONDS) -> None:
    hand["action_deadline"] = datetime.fromtimestamp(
        now_epoch + max(1, int(seconds)), timezone.utc
    ).isoformat()


def settle_expired_turn(state: dict, engine, *, now_epoch: float | None = None) -> str | None:
    """Consume one forced card or fold an expired actor.

    Returns timebank, fold or None. Ring and Sit&Go schedulers share this rule.
    """
    if state.get("status") != "playing":
        return None
    hand = state.get("hand") or {}
    player = _active_player(state)
    if not player:
        return None
    legal = engine.legal_actions(state, player["user_id"])
    if not legal.get("can_act"):
        return None

    now_epoch = time.time() if now_epoch is None else float(now_epoch)
    cards = _ensure_cards(player)
    if cards > 0:
        remaining = cards - 1
        player["timebank_cards"] = remaining
        hand["timebank_stage"] = int(hand.get("timebank_stage") or 0) + 1
        _set_deadline(hand, now_epoch=now_epoch)
        hand.setdefault("log", []).append(
            f"{player['name']} uses time bank · {remaining} left"
        )
        return "timebank"

    hand.setdefault("log", []).append(
        f"{player['name']} {FORCED_FOLD_LOG_SUFFIX}"
    )
    engine.apply_action(state, player["user_id"], "fold")
    return "fold"


def _wrap_public_state(owner) -> None:
    original = owner.public_state
    if getattr(original, "_jj_timebank_public", False):
        return

    def public_state(state, viewer_id=None):
        out = original(state, viewer_id)
        if isinstance(out, dict):
            for item in out.get("seats", []):
                item["timebank_cards"] = max(
                    0, min(TIME_BANK_CARDS, int(item.get("timebank_cards", TIME_BANK_CARDS) or 0))
                )
            hand = out.get("hand")
            if isinstance(hand, dict):
                hand["timebank_stage"] = int(hand.get("timebank_stage") or 0)
        return out

    public_state._jj_timebank_public = True
    owner.public_state = public_state


def _wrap_seat_player(owner) -> None:
    original = owner.seat_player
    if getattr(original, "_jj_timebank_seating", False):
        return

    def seat_player(state, *args, **kwargs):
        result = original(state, *args, **kwargs)
        user_id = kwargs.get("user_id")
        if user_id is None and args:
            user_id = args[0]
        for player in state.get("seats", []):
            if user_id is None or int(player.get("user_id", -1)) == int(user_id):
                player.setdefault("timebank_cards", TIME_BANK_CARDS)
        return result

    seat_player._jj_timebank_seating = True
    owner.seat_player = seat_player


def _install_deadline(server) -> None:
    original = server.arm_action_deadline
    if getattr(original, "_jj_timebank_deadline", False):
        return

    def arm_action_deadline(state, seconds: int = ACTION_SECONDS):
        hand = state.get("hand")
        player = _active_player(state)
        if player:
            _ensure_cards(player)
        result = original(state, ACTION_SECONDS)
        if hand:
            hand["timebank_stage"] = 0
        return result

    arm_action_deadline._jj_timebank_deadline = True
    server.arm_action_deadline = arm_action_deadline


def _install_ring_timeout(server, engine) -> None:
    async def timeout_loop():
        while True:
            await asyncio.sleep(0.25)
            try:
                for tid, _ in server.db.FIXED_TABLES:
                    changed = False
                    async with server.get_table_lock(tid):
                        try:
                            state = server.load_table(tid)
                        except Exception:
                            continue
                        if server.prune_idle_players(state, tid):
                            server.save_table(state)
                            changed = True

                        hand = state.get("hand") or {}
                        deadline = _deadline_epoch(hand)
                        now_epoch = time.time()
                        if (
                            state.get("status") == "playing"
                            and deadline is not None
                            and now_epoch >= deadline
                        ):
                            outcome = settle_expired_turn(
                                state, engine, now_epoch=now_epoch
                            )
                            if outcome:
                                if outcome == "fold":
                                    server.arm_action_deadline(state)
                                server.save_table(state)
                                changed = True
                    if changed:
                        await server.hub.broadcast(tid)
            except asyncio.CancelledError:
                raise
            except Exception:
                pass

    timeout_loop._jj_timebank_timeout = True
    server.timeout_loop = timeout_loop


def _install_sitngo_engine_factory(runtime_module) -> None:
    original_make_engine = runtime_module.make_engine
    if getattr(original_make_engine, "_jj_timebank_engine_factory", False):
        return

    def make_engine():
        engine = original_make_engine()
        _wrap_seat_player(engine)
        _wrap_public_state(engine)
        return engine

    make_engine._jj_timebank_engine_factory = True
    runtime_module.make_engine = make_engine


def _install_sitngo_tick(runtime_module) -> None:
    runtime_cls = runtime_module.TournamentRuntime
    original_tick = runtime_cls.tick
    if getattr(original_tick, "_jj_timebank_tick", False):
        return

    async def tick(self, eid, *, now=None, recover=False):
        if recover:
            return await original_tick(self, eid, now=now, recover=recover)

        now_epoch = time.time() if now is None else float(now)
        try:
            probe = self.load(eid)
        except Exception:
            return await original_tick(self, eid, now=now, recover=recover)

        tournament = probe.get("tournament") or {}
        hand = probe.get("hand") or {}
        deadline = _deadline_epoch(hand)
        if (
            tournament.get("status") == "running"
            and probe.get("status") == "playing"
            and deadline is not None
            and now_epoch >= deadline + SITNGO_TIMEOUT_GRACE_SECONDS
        ):
            async with self.server.get_table_lock(eid):
                state = self.load(eid)
                hand = state.get("hand") or {}
                deadline = _deadline_epoch(hand)
                if (
                    state.get("status") == "playing"
                    and deadline is not None
                    and now_epoch >= deadline + SITNGO_TIMEOUT_GRACE_SECONDS
                ):
                    turn_id = str(hand.get("turn_id") or "")
                    pending_map = getattr(self, "_pending_action_arrivals", {})
                    pending = pending_map.get((eid, turn_id)) if turn_id else None
                    if pending and float(pending.get("earliest", now_epoch + 1)) <= deadline:
                        return now_epoch + 0.05

                    outcome = settle_expired_turn(
                        state, self.engine, now_epoch=now_epoch
                    )
                    if outcome:
                        if outcome == "fold":
                            self.server.arm_action_deadline(state)
                        self.save(state, notify=False)

        return await original_tick(self, eid, now=now, recover=recover)

    tick._jj_timebank_tick = True
    runtime_cls.tick = tick


def install(server, ring_engine, sitngo_runtime_module=None) -> None:
    """Install Ring and optional Sit&Go time-bank behavior."""
    _wrap_seat_player(server)
    _wrap_seat_player(ring_engine)
    _wrap_public_state(server)
    _wrap_public_state(ring_engine)
    _install_deadline(server)
    _install_ring_timeout(server, ring_engine)
    if sitngo_runtime_module is not None:
        _install_sitngo_engine_factory(sitngo_runtime_module)
        _install_sitngo_tick(sitngo_runtime_module)


__all__ = [
    "ACTION_SECONDS",
    "TIME_BANK_CARDS",
    "SITNGO_TIMEOUT_GRACE_SECONDS",
    "settle_expired_turn",
    "install",
]
