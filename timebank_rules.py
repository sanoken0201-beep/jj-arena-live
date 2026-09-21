from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import Any

BASE_ACTION_SECONDS = 30
TIMEBANK_CARD_SECONDS = 30
TIMEBANK_CARDS = 3
MARKER = "jj forced timebank cards 2026-09-21"


def _player_for_action(state: dict[str, Any]) -> dict[str, Any] | None:
    hand = state.get("hand") or {}
    seat = hand.get("action_seat")
    return next((p for p in state.get("seats", []) if p.get("seat") == seat), None)


def ensure_cards(player: dict[str, Any] | None) -> None:
    if player is None:
        return
    if "timebank_cards_remaining" not in player:
        player["timebank_cards_remaining"] = TIMEBANK_CARDS
    player["timebank_cards_total"] = TIMEBANK_CARDS


def _set_deadline(state: dict[str, Any], seconds: int, *, source: str) -> None:
    hand = state.get("hand")
    if not hand:
        return
    if state.get("status") == "playing" and hand.get("action_seat") is not None:
        hand["action_deadline"] = (
            datetime.now(timezone.utc) + timedelta(seconds=int(seconds))
        ).isoformat()
        hand["action_clock_source"] = source
    else:
        hand["action_deadline"] = None
        hand["action_clock_source"] = None


def install_ring(server, engine) -> None:
    if getattr(server, "_jj_timebank_ring_installed", False):
        return

    original_deadline = server.arm_action_deadline

    def arm_action_deadline(state, seconds: int = BASE_ACTION_SECONDS):
        player = _player_for_action(state)
        ensure_cards(player)
        # Explicit callers may still request a shorter/longer safety deadline,
        # but the normal default is the product contract: 30 seconds.
        requested = BASE_ACTION_SECONDS if seconds == 45 else int(seconds)
        _set_deadline(state, requested, source="base")

    server.arm_action_deadline = arm_action_deadline

    async def timeout_loop():
        while True:
            await asyncio.sleep(0.5)
            try:
                for table_id, _ in server.db.FIXED_TABLES:
                    changed = False
                    async with server.get_table_lock(table_id):
                        try:
                            state = server.load_table(table_id)
                        except Exception:
                            continue

                        if server.prune_idle_players(state, table_id):
                            server.save_table(state)
                            changed = True

                        hand = state.get("hand") or {}
                        deadline_raw = hand.get("action_deadline")
                        if (
                            state.get("status") == "playing"
                            and deadline_raw
                            and datetime.now(timezone.utc) >= datetime.fromisoformat(deadline_raw)
                        ):
                            player = _player_for_action(state)
                            if player:
                                ensure_cards(player)
                                legal = engine.legal_actions(state, player["user_id"])
                                if legal.get("can_act"):
                                    remaining = max(0, int(player.get("timebank_cards_remaining") or 0))
                                    if remaining > 0:
                                        player["timebank_cards_remaining"] = remaining - 1
                                        hand["log"].append(
                                            f"{player['name']} timebank · {remaining - 1} card(s) left"
                                        )
                                        _set_deadline(
                                            state,
                                            TIMEBANK_CARD_SECONDS,
                                            source="timebank",
                                        )
                                    else:
                                        engine.apply_action(state, player["user_id"], "fold")
                                        if state.get("hand"):
                                            state["hand"]["log"].append(
                                                f"{player['name']} timed out · forced fold"
                                            )
                                        server.arm_action_deadline(state)
                                    server.save_table(state)
                                    changed = True
                    if changed:
                        await server.hub.broadcast(table_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                # Preserve the existing fail-open lifecycle policy.
                pass

    server.timeout_loop = timeout_loop
    server._jj_timebank_ring_installed = True
    server._jj_timebank_original_deadline = original_deadline


def install_sitngo(runtime_module) -> None:
    runtime_cls = runtime_module.TournamentRuntime
    if getattr(runtime_cls, "_jj_timebank_installed", False):
        return

    original_tick = runtime_cls.tick
    original_init = runtime_cls.__init__

    def init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        server = self.server
        if not getattr(server, "_jj_timebank_sng_deadline_installed", False):
            def arm_action_deadline(state, seconds: int = BASE_ACTION_SECONDS):
                player = _player_for_action(state)
                ensure_cards(player)
                requested = BASE_ACTION_SECONDS if seconds == 45 else int(seconds)
                _set_deadline(state, requested, source="base")
                hand = state.get("hand") or {}
                # Preserve Sit&Go turn-token renewal when present.
                try:
                    import sitngo_action_safety
                    sitngo_action_safety._renew_turn_id(state)
                except Exception:
                    pass
            server.arm_action_deadline = arm_action_deadline
            server._jj_timebank_sng_deadline_installed = True

    async def tick(self, eid, *, now=None, recover=False):
        now = time.time() if now is None else float(now)
        if recover:
            return await original_tick(self, eid, now=now, recover=True)

        s = self.server
        try:
            async with s.get_table_lock(eid):
                state = self.load(eid)
                hand = state.get("hand") or {}
                if state.get("status") == "playing" and hand.get("action_deadline"):
                    deadline = datetime.fromisoformat(hand["action_deadline"]).timestamp()
                    grace = 0.35
                    try:
                        import sitngo_action_safety
                        grace = float(sitngo_action_safety.TIMEOUT_SETTLEMENT_GRACE_SECONDS)
                    except Exception:
                        pass

                    if now >= deadline + grace:
                        turn_id = str(hand.get("turn_id") or "")
                        pending = getattr(self, "_pending_action_arrivals", {}).get((eid, turn_id)) if turn_id else None
                        if pending and float(pending.get("earliest", 1e30)) <= deadline:
                            return await original_tick(self, eid, now=now, recover=False)

                        player = _player_for_action(state)
                        if player:
                            ensure_cards(player)
                            legal = self.engine.legal_actions(state, player["user_id"])
                            if legal.get("can_act"):
                                remaining = max(0, int(player.get("timebank_cards_remaining") or 0))
                                if remaining > 0:
                                    player["timebank_cards_remaining"] = remaining - 1
                                    hand.setdefault("log", []).append(
                                        f"{player['name']} timebank · {remaining - 1} card(s) left"
                                    )
                                    hand["action_deadline"] = datetime.fromtimestamp(
                                        now + TIMEBANK_CARD_SECONDS, timezone.utc
                                    ).isoformat()
                                    hand["action_clock_source"] = "timebank"
                                    self.save(state)
                                    await s.hub.broadcast(eid)
                                    return now + TIMEBANK_CARD_SECONDS + grace
                                self.engine.apply_action(state, player["user_id"], "fold")
                                if state.get("hand"):
                                    state["hand"].setdefault("log", []).append(
                                        f"{player['name']} timed out · forced fold"
                                    )
                                s.arm_action_deadline(state)
                                self.save(state)
                                await s.hub.broadcast(eid)
                                return now + 0.05
        except asyncio.CancelledError:
            raise

        return await original_tick(self, eid, now=now, recover=False)

    runtime_cls.__init__ = init
    runtime_cls.tick = tick
    runtime_cls._jj_timebank_installed = True


__all__ = [
    "BASE_ACTION_SECONDS",
    "TIMEBANK_CARD_SECONDS",
    "TIMEBANK_CARDS",
    "MARKER",
    "ensure_cards",
    "install_ring",
    "install_sitngo",
]
