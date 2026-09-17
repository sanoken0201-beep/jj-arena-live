"""Finish-state guard for Sit&Go late registration.

If a tournament reaches one survivor before its configured late-registration
window closes and an unused unique-player seat remains, it must not become final
while the lobby still advertises registration. Keep the table in a waiting state
until the deadline, or resume immediately if a queued entrant arrives.
"""
from __future__ import annotations

import time


def install(sitngo_runtime, entry_rules) -> None:
    if getattr(sitngo_runtime, "_JJ_ENTRY_FINISH_GUARD_INSTALLED", False):
        return
    runtime_cls = sitngo_runtime.TournamentRuntime
    original_finish = runtime_cls.finish

    def finish(self, state):
        original_finish(self, state)
        tournament = state.get("tournament") or {}
        # A zero-minute policy is the legacy freezeout contract. Do not infer an
        # open window from timestamps alone (tests/recovery may use simulated time).
        if int(tournament.get("late_registration_minutes") or 0) <= 0:
            return
        deadline = float(tournament.get("entry_window_deadline_epoch") or 0)
        now = time.time()
        if deadline <= now:
            return
        if int(tournament.get("entrants") or 0) >= int(state.get("max_seats") or 6):
            return
        # A queued entrant should activate immediately between hands, not wait
        # until the end of the registration window.
        if entry_rules._pending_rows(self, str(state.get("id"))):
            return

        if tournament.get("status") == "finished":
            tournament["results"] = [
                result for result in tournament.get("results", [])
                if int(result.get("place") or 0) != 1
            ]
            tournament["status"] = "running"
            tournament.pop("finished_at", None)
            tournament["finish_grace_hand_id"] = (state.get("hand") or {}).get("id")
            tournament["reentry_grace_until_epoch"] = deadline
            state["session_active"] = False
            state["next_hand_at_epoch"] = deadline
            return

        # The entry-rules layer may already have reopened the tournament for a
        # busted player's short re-entry grace. If unused late-registration seats
        # remain, the advertised late-registration deadline is the stronger rule.
        if tournament.get("status") == "running" and tournament.get("reentry_grace_until_epoch"):
            tournament["reentry_grace_until_epoch"] = deadline
            state["session_active"] = False
            state["next_hand_at_epoch"] = deadline

    runtime_cls.finish = finish
    sitngo_runtime._JJ_ENTRY_FINISH_GUARD_INSTALLED = True


__all__ = ["install"]
