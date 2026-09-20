"""Sit&Go turn-token and timeout-boundary safety.

This layer is installed before ``sitngo.install()`` constructs TournamentRuntime.
It keeps the immutable ring core untouched while adding three tournament-only
contracts:

* every actionable turn has a server-generated ``turn_id``;
* browser actions must echo ``action_id``, ``hand_id`` and ``turn_id``;
* a request that reaches the server before its deadline wins over the automatic
  timeout even if both contend for the same table lock at the boundary.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import Depends, HTTPException

TIMEOUT_SETTLEMENT_GRACE_SECONDS = 0.35
TURN_UI_MARKER = "jj sng turn safety 2026-09-18"


def _deadline_epoch(hand: dict) -> float | None:
    raw = hand.get("action_deadline")
    if not raw:
        return None
    return datetime.fromisoformat(raw).timestamp()


def _renew_turn_id(state: dict) -> None:
    hand = state.get("hand") or {}
    if state.get("status") != "playing" or hand.get("action_seat") is None:
        if hand:
            hand["turn_id"] = None
        return
    seq = int(state.get("_turn_seq") or 0) + 1
    state["_turn_seq"] = seq
    hand_id = str(hand.get("id") or "hand")
    hand["turn_id"] = f"{hand_id}:{seq}"


def _install_deadline_wrapper(server) -> None:
    if getattr(server, "_jj_sng_turn_deadline_patched", False):
        return
    original = server.arm_action_deadline

    def arm_action_deadline(state, seconds: int = 45):
        result = original(state, seconds)
        if state.get("tournament"):
            _renew_turn_id(state)
        return result

    server.arm_action_deadline = arm_action_deadline
    server._jj_sng_turn_deadline_patched = True


def install(runtime_module) -> None:
    runtime_cls = runtime_module.TournamentRuntime
    if getattr(runtime_cls, "_jj_turn_safety_installed", False):
        return

    original_init = runtime_cls.__init__
    original_install_routes = runtime_cls.install_routes
    original_public = runtime_cls.public
    legacy_tick = runtime_cls.tick
    import sitngo_observability

    def init(self, service, ring_engine):
        self._pending_action_arrivals = {}
        _install_deadline_wrapper(service.server)
        original_init(self, service, ring_engine)

    def _pending_enter(self, event_id: str, turn_id: str, received_at: float):
        key = (event_id, turn_id)
        entry = self._pending_action_arrivals.get(key)
        if entry is None:
            self._pending_action_arrivals[key] = {"earliest": received_at, "count": 1}
        else:
            entry["earliest"] = min(float(entry["earliest"]), received_at)
            entry["count"] = int(entry["count"]) + 1
        return key

    def _pending_leave(self, key):
        entry = self._pending_action_arrivals.get(key)
        if not entry:
            return
        entry["count"] = int(entry["count"]) - 1
        if entry["count"] <= 0:
            self._pending_action_arrivals.pop(key, None)

    def install_routes(self):
        original_install_routes(self)
        from pydantic import create_model

        s = self.server
        app = self.service.app
        action_model = create_model(
            "SitNGoTurnActionIn",
            __base__=s.ActionIn,
            hand_id=(str | None, None),
            turn_id=(str | None, None),
        )

        async def guarded_action(table_id, payload, user=Depends(s.current_user)):
            if not table_id.startswith("sng-"):
                return await s.action(table_id, payload, user)

            received_at = time.time()
            receipt = str(payload.action_id or "").strip()
            hand_id = str(payload.hand_id or "").strip()
            turn_id = str(payload.turn_id or "").strip()
            if not receipt or not hand_id or not turn_id:
                sitngo_observability.record(self.db, "missing_tokens")
                raise HTTPException(409, "画面を再読み込みしてから操作してください")

            pending_key = _pending_enter(self, table_id, turn_id, received_at)
            try:
                async with s.get_table_lock(table_id):
                    state = self.load(table_id)
                    processed = list(state.get("_processed_action_ids") or [])
                    receipt_key = f"{user['id']}:{receipt}"
                    if receipt_key in processed:
                        sitngo_observability.record(self.db, "duplicate_action")
                        return self.public(state, user["id"])

                    hand = state.get("hand") or {}
                    if hand_id != str(hand.get("id") or ""):
                        sitngo_observability.record(self.db, "stale_hand")
                        raise HTTPException(409, "次のハンドに進みました。現在の手札を確認してください")
                    if turn_id != str(hand.get("turn_id") or ""):
                        sitngo_observability.record(self.db, "stale_turn")
                        raise HTTPException(409, "操作順が更新されました。現在のアクションを確認してください")

                    deadline = _deadline_epoch(hand)
                    if deadline is None or received_at > deadline:
                        sitngo_observability.record(self.db, "late_action")
                        self.signal()
                        raise HTTPException(409, "操作時間を過ぎました。最新の状態を確認してください")

                    try:
                        self.engine.apply_action(state, user["id"], payload.action, payload.amount)
                    except ValueError as exc:
                        raise HTTPException(400, str(exc)) from exc

                    state["_processed_action_ids"] = (processed + [receipt_key])[-120:]
                    s.arm_action_deadline(state)
                    self.save(state)
                await s.hub.broadcast(table_id)
                return self.public(state, user["id"])
            finally:
                _pending_leave(self, pending_key)

        guarded_action.__annotations__ = {"table_id": str, "payload": action_model}
        app.post("/api/tables/{table_id}/action")(guarded_action)
        replacement = app.router.routes.pop()
        matches = [
            i
            for i, route in enumerate(app.router.routes)
            if getattr(route, "path", "") == "/api/tables/{table_id}/action"
            and "POST" in (getattr(route, "methods", None) or set())
        ]
        if not matches:
            raise RuntimeError("Sit&Go action route precedence target is missing")
        app.router.routes.insert(min(matches), replacement)

    async def tick(self, eid, *, now=None, recover=False):
        """12-hand scheduler plus race-safe tournament timeout settlement."""
        import sitngo_hand_levels

        now = time.time() if now is None else float(now)
        probe = self.load(eid)
        if (probe.get("tournament") or {}).get("level_mode") != sitngo_hand_levels.LEVEL_MODE:
            return await legacy_tick(self, eid, now=now, recover=recover)

        s = self.server
        protected_timeout = False
        async with s.get_table_lock(eid):
            state = self.load(eid)
            tournament = state["tournament"]
            if tournament["status"] != "running":
                return None

            previous = float(tournament.get("clock_at_epoch") or now)
            if recover:
                sitngo_observability.record(self.db, "restart_recovery")
                delta = max(0.0, now - previous)
                hand = state.get("hand") or {}
                if hand.get("action_deadline"):
                    deadline = datetime.fromisoformat(hand["action_deadline"]).timestamp() + delta
                    hand["action_deadline"] = datetime.fromtimestamp(deadline, timezone.utc).isoformat()
                for obj, key in (
                    (hand, "runout_due_at_epoch"),
                    (state, "next_hand_at_epoch"),
                    (state, "showdown_hold_until_epoch"),
                ):
                    if obj.get(key):
                        obj[key] += delta
            else:
                tournament["elapsed_seconds"] = float(tournament.get("elapsed_seconds") or 0) + max(0.0, now - previous)
            tournament["clock_at_epoch"] = now

            hand = state.get("hand") or {}
            if not recover and state["status"] == "playing":
                if hand.get("forced_runout") and float(hand.get("runout_due_at_epoch") or 0) <= now:
                    self.engine.advance_forced_runout(state)
                else:
                    deadline = _deadline_epoch(hand)
                    if deadline is not None and now >= deadline + TIMEOUT_SETTLEMENT_GRACE_SECONDS:
                        turn_id = str(hand.get("turn_id") or "")
                        pending = self._pending_action_arrivals.get((eid, turn_id)) if turn_id else None
                        if pending and float(pending["earliest"]) <= deadline:
                            sitngo_observability.record(self.db, "timeout_boundary_protected")
                            protected_timeout = True
                        else:
                            player = next((p for p in state["seats"] if p["seat"] == hand.get("action_seat")), None)
                            if player:
                                legal = self.engine.legal_actions(state, player["user_id"])
                                if legal.get("can_act"):
                                    sitngo_observability.record(self.db, "timeout_auto_action")
                                    self.engine.apply_action(
                                        state,
                                        player["user_id"],
                                        "check" if legal.get("can_check") else "fold",
                                    )
                                    s.arm_action_deadline(state)
            elif not recover and state["status"] == "waiting" and float(state.get("next_hand_at_epoch") or 0) <= now:
                levels = list(tournament.get("structure") or [])
                if not levels:
                    raise RuntimeError("Sit&Go blind structure is empty")
                completed_hands = max(0, int(state.get("hand_no") or 0))
                index = sitngo_hand_levels.level_index_for_completed_hands(completed_hands, len(levels))
                level = levels[index]
                tournament.update(
                    level=index + 1,
                    bb_ante=int(level["bb_ante"]),
                    level_started_hand_no=index * sitngo_hand_levels.HANDS_PER_LEVEL + 1,
                    hands_per_level=sitngo_hand_levels.HANDS_PER_LEVEL,
                    level_mode=sitngo_hand_levels.LEVEL_MODE,
                )
                state.update(
                    small_blind=int(level["small_blind"]),
                    big_blind=int(level["big_blind"]),
                )
                self.engine.start_hand(state)
                s.arm_action_deadline(state)

            self.save(state, notify=False)
            hand = state.get("hand") or {}
            deadlines = [now + 5]
            if state["status"] == "playing":
                deadline = _deadline_epoch(hand)
                if deadline is not None:
                    deadlines.append(deadline + TIMEOUT_SETTLEMENT_GRACE_SECONDS)
                if hand.get("runout_due_at_epoch"):
                    deadlines.append(float(hand["runout_due_at_epoch"]))
                if protected_timeout:
                    deadlines.append(now + 0.05)
            elif tournament["status"] == "running":
                deadlines.append(float(state.get("next_hand_at_epoch") or now + 1.6))
        await s.hub.broadcast(eid)
        return min(deadlines)

    def public(self, state, viewer=None):
        value = original_public(self, state, viewer)
        hand = state.get("hand") or {}
        active = state.get("status") == "playing" and hand.get("action_seat") is not None
        value["turn_id"] = hand.get("turn_id") if active else None
        if isinstance(value.get("hand"), dict):
            value["hand"]["turn_id"] = value["turn_id"]
        return value

    runtime_cls.__init__ = init
    runtime_cls.install_routes = install_routes
    runtime_cls._pending_enter = _pending_enter
    runtime_cls._pending_leave = _pending_leave
    runtime_cls.tick = tick
    runtime_cls.public = public
    runtime_cls._jj_turn_safety_installed = True


__all__ = [
    "TIMEOUT_SETTLEMENT_GRACE_SECONDS",
    "TURN_UI_MARKER",
    "install",
]
