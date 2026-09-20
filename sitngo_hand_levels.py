"""Hand-count blind progression for JJ Arena Sit&Go tournaments.

New tournaments advance one blind level after every 12 completed hands.  The
change is intentionally isolated from the immutable ring-game core and from
already-running legacy tournaments: only states created with ``level_mode`` set
to ``hands`` use this scheduler.

The persisted minute fields remain as schema/rollback compatibility metadata;
they are not consulted for blind progression in hand-count tournaments.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone

HANDS_PER_LEVEL = 12
LEVEL_MODE = "hands"


def level_index_for_completed_hands(completed_hands: int, level_count: int) -> int:
    """Return the zero-based level used by the *next* hand."""
    count = max(1, int(level_count))
    completed = max(0, int(completed_hands))
    return min(completed // HANDS_PER_LEVEL, count - 1)


def _patch_service_contract(sitngo_module) -> None:
    service_cls = sitngo_module.SitNGoService
    if getattr(service_cls, "_jj_hand_levels_contract", False):
        return

    original_payload = service_cls._event_payload
    original_admin_events = service_cls.admin_events

    def event_payload(self, row, user_id=None, *, admin=False):
        payload = original_payload(self, row, user_id, admin=admin)
        tournament = payload.get("tournament") or {}
        if str(payload.get("status")) in {"running", "finished"} and tournament:
            mode = str(tournament.get("level_mode") or "time")
            payload["level_mode"] = mode
            payload["hands_per_level"] = int(tournament.get("hands_per_level") or HANDS_PER_LEVEL) if mode == LEVEL_MODE else None
        else:
            payload["level_mode"] = LEVEL_MODE
            payload["hands_per_level"] = HANDS_PER_LEVEL
        return payload

    def admin_events(self, actor_id: int):
        result = original_admin_events(self, actor_id)
        defaults = result.setdefault("defaults", {})
        defaults["level_mode"] = LEVEL_MODE
        defaults["hands_per_level"] = HANDS_PER_LEVEL
        return result

    service_cls._event_payload = event_payload
    service_cls.admin_events = admin_events
    service_cls._jj_hand_levels_contract = True


def _patch_runtime(runtime_module) -> None:
    runtime_cls = runtime_module.TournamentRuntime
    if getattr(runtime_cls, "_jj_hand_levels_installed", False):
        return

    original_create = runtime_cls.create
    original_tick = runtime_cls.tick
    original_public = runtime_cls.public

    def create(self, con, event, participants, now):
        original_create(self, con, event, participants, now)
        row = con.execute(
            "SELECT state_json,revision FROM sitngo_games WHERE event_id=?",
            (event["id"],),
        ).fetchone()
        if not row:
            return
        state = json.loads(row["state_json"])
        tournament = state.get("tournament") or {}
        if tournament.get("level_mode") == LEVEL_MODE:
            return
        tournament.update(
            level_mode=LEVEL_MODE,
            hands_per_level=HANDS_PER_LEVEL,
            level_started_hand_no=1,
        )
        state["tournament"] = tournament
        updated = con.execute(
            "UPDATE sitngo_games SET state_json=?,updated_at=? WHERE event_id=? AND revision=?",
            (json.dumps(state, ensure_ascii=False), self.db.utcnow(), event["id"], row["revision"]),
        )
        if updated.rowcount != 1:
            raise RuntimeError("Sit&Go hand-level initialization lost update")

    async def tick(self, eid, *, now=None, recover=False):
        probe = self.load(eid)
        if (probe.get("tournament") or {}).get("level_mode") != LEVEL_MODE:
            return await original_tick(self, eid, now=now, recover=recover)

        server = self.server
        now = time.time() if now is None else float(now)
        async with server.get_table_lock(eid):
            state = self.load(eid)
            tournament = state["tournament"]
            if tournament["status"] != "running":
                return None

            previous = float(tournament.get("clock_at_epoch") or now)
            if recover:
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
                # Duration remains useful telemetry, but it never selects blinds.
                tournament["elapsed_seconds"] = float(tournament.get("elapsed_seconds") or 0) + max(0.0, now - previous)
            tournament["clock_at_epoch"] = now

            hand = state.get("hand") or {}
            if not recover and state["status"] == "playing":
                if hand.get("forced_runout") and float(hand.get("runout_due_at_epoch") or 0) <= now:
                    self.engine.advance_forced_runout(state)
                elif hand.get("action_deadline") and datetime.fromisoformat(hand["action_deadline"]).timestamp() <= now:
                    player = next((p for p in state["seats"] if p["seat"] == hand.get("action_seat")), None)
                    if player:
                        legal = self.engine.legal_actions(state, player["user_id"])
                        self.engine.apply_action(
                            state,
                            player["user_id"],
                            "check" if legal.get("can_check") else "fold",
                        )
                        server.arm_action_deadline(state)
            elif not recover and state["status"] == "waiting" and float(state.get("next_hand_at_epoch") or 0) <= now:
                levels = list(tournament.get("structure") or [])
                if not levels:
                    raise RuntimeError("Sit&Go blind structure is empty")
                completed_hands = max(0, int(state.get("hand_no") or 0))
                index = level_index_for_completed_hands(completed_hands, len(levels))
                level = levels[index]
                tournament.update(
                    level=index + 1,
                    bb_ante=int(level["bb_ante"]),
                    level_started_hand_no=index * HANDS_PER_LEVEL + 1,
                    hands_per_level=HANDS_PER_LEVEL,
                    level_mode=LEVEL_MODE,
                )
                state.update(
                    small_blind=int(level["small_blind"]),
                    big_blind=int(level["big_blind"]),
                )
                self.engine.start_hand(state)
                server.arm_action_deadline(state)

            self.save(state, notify=False)
            hand = state.get("hand") or {}
            deadlines = [now + 5]
            if state["status"] == "playing":
                if hand.get("action_deadline"):
                    deadlines.append(datetime.fromisoformat(hand["action_deadline"]).timestamp())
                if hand.get("runout_due_at_epoch"):
                    deadlines.append(float(hand["runout_due_at_epoch"]))
            elif tournament["status"] == "running":
                deadlines.append(float(state.get("next_hand_at_epoch") or now + 1.6))
        await server.hub.broadcast(eid)
        return min(deadlines)

    def public(self, state, viewer=None):
        value = original_public(self, state, viewer)
        tournament = value.get("tournament") or {}
        if tournament.get("level_mode") != LEVEL_MODE:
            return value

        level_no = max(1, int(tournament.get("level") or 1))
        hand_no = max(0, int(state.get("hand_no") or 0))
        first_hand = (level_no - 1) * HANDS_PER_LEVEL + 1
        hand_in_level = max(0, min(HANDS_PER_LEVEL, hand_no - first_hand + 1))
        final_level = level_no >= len(tournament.get("structure") or [])
        tournament.update(
            next_level_at=None,
            level_mode=LEVEL_MODE,
            hands_per_level=HANDS_PER_LEVEL,
            hand_in_level=hand_in_level,
            hands_until_level_up=None if final_level else max(0, HANDS_PER_LEVEL - hand_in_level),
            next_level_hand_no=None if final_level else level_no * HANDS_PER_LEVEL + 1,
        )
        value["tournament"] = tournament
        return value

    runtime_cls.create = create
    runtime_cls.tick = tick
    runtime_cls.public = public
    runtime_cls._jj_hand_levels_installed = True


def install(sitngo_module, runtime_module) -> None:
    """Install the fixed 12-hand contract before TournamentRuntime is created."""
    _patch_service_contract(sitngo_module)
    _patch_runtime(runtime_module)


__all__ = [
    "HANDS_PER_LEVEL",
    "LEVEL_MODE",
    "install",
    "level_index_for_completed_hands",
]
