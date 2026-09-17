"""Restrict terminal Sit&Go re-entry grace to the newly busted player(s).

The general re-entry window remains available while the tournament is naturally
continuing. When a hand would otherwise leave one survivor, however, the runtime
briefly reopens the event only so the player(s) eliminated by that terminal hand
can decide whether to re-enter. Older eliminated players must not use that short
finish grace, and the API must reject requests after the grace timestamp even if
the lifecycle tick has not finalized the event yet.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import HTTPException


def install(sitngo_runtime, entry_rules) -> None:
    if getattr(sitngo_runtime, "_JJ_TERMINAL_REENTRY_GUARD_INSTALLED", False):
        return

    import sitngo

    runtime_cls = sitngo_runtime.TournamentRuntime
    service_cls = sitngo.SitNGoService
    original_finish = runtime_cls.finish
    original_payload = service_cls._event_payload
    original_reenter = service_cls.reenter

    def finish(self, state):
        original_finish(self, state)
        tournament = state.get("tournament") or {}
        grace = float(tournament.get("reentry_grace_until_epoch") or 0)
        if tournament.get("status") != "running" or grace <= 0:
            return
        hand = state.get("hand") or {}
        current_hand_no = int(state.get("hand_no") or 0)
        maximum = int(tournament.get("max_reentries") or 0)
        if maximum <= 0:
            return
        allowed: list[int] = []
        for result in tournament.get("results", []):
            if int(result.get("place") or 0) <= 1 or int(result.get("hand_no") or -1) != current_hand_no:
                continue
            uid = int(result["user_id"])
            reg = entry_rules._registration_row(self, str(state["id"]), uid)
            if reg and int(reg.get("reentry_count") or 0) < maximum:
                allowed.append(uid)
        if allowed:
            tournament["terminal_reentry_user_ids"] = sorted(set(allowed))
            tournament["terminal_reentry_hand_id"] = hand.get("id")

    def event_payload(self, row, user_id=None, *, admin=False):
        payload = original_payload(self, row, user_id, admin=admin)
        if not payload.get("can_reenter") or user_id is None:
            return payload
        try:
            state = self.runtime.load(str(row["id"]))
        except HTTPException:
            return payload
        tournament = state.get("tournament") or {}
        grace = float(tournament.get("reentry_grace_until_epoch") or 0)
        if grace > 0:
            allowed = {int(uid) for uid in tournament.get("terminal_reentry_user_ids") or []}
            payload["can_reenter"] = bool(time.time() < grace and int(user_id) in allowed)
            payload["terminal_reentry_deadline"] = (
                datetime.fromtimestamp(grace, timezone.utc).isoformat()
                if int(user_id) in allowed else None
            )
        return payload

    def reenter(self, event_id: str, user_id: int):
        state = self.runtime.load(event_id)
        tournament = state.get("tournament") or {}
        grace = float(tournament.get("reentry_grace_until_epoch") or 0)
        if grace > 0:
            allowed = {int(uid) for uid in tournament.get("terminal_reentry_user_ids") or []}
            if int(user_id) not in allowed:
                raise HTTPException(409, "終局時のリエントリー猶予は直前のハンドで敗退したプレイヤーのみ利用できます")
            if time.time() >= grace:
                raise HTTPException(409, "終局時のリエントリー受付時間を過ぎました")
        return original_reenter(self, event_id, user_id)

    runtime_cls.finish = finish
    service_cls._event_payload = event_payload
    service_cls.reenter = reenter
    sitngo_runtime._JJ_TERMINAL_REENTRY_GUARD_INSTALLED = True


__all__ = ["install"]
