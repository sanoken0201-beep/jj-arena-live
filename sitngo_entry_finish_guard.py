"""Finish-state guard for Sit&Go late registration and re-entry rights.

A configured post-start entry window is authoritative. If a tournament reaches
one survivor while an unused unique-player seat or an eligible re-entry remains,
the result is not final until that deadline. Pending entries activate immediately
between hands; otherwise the table waits without resetting the blind clock.
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

        event_id = str(state.get("id"))
        pending = entry_rules._pending_rows(self, event_id)
        if pending:
            # Queued entrants are consumed by tick immediately; extending the
            # sleep here would incorrectly postpone an already accepted entry.
            return

        unused_unique_seat = int(tournament.get("entrants") or 0) < int(state.get("max_seats") or 6)
        maximum = int(tournament.get("max_reentries") or 0)
        eligible_reentry = False
        if maximum > 0:
            with self.db.connect() as con:
                row = con.execute(
                    "SELECT 1 ok FROM sitngo_registrations "
                    "WHERE event_id=? AND status='finished' AND reentry_count<? LIMIT 1",
                    (event_id, maximum),
                ).fetchone()
            eligible_reentry = bool(row)
        if not unused_unique_seat and not eligible_reentry:
            return

        if tournament.get("status") == "finished":
            tournament["results"] = [
                result for result in tournament.get("results", [])
                if int(result.get("place") or 0) != 1
            ]
            tournament["status"] = "running"
            tournament.pop("finished_at", None)
            tournament["finish_grace_hand_id"] = (state.get("hand") or {}).get("id")

        # The inner entry-rules layer may have created a shorter grace. The
        # administrator-facing contract is stronger: every advertised late-entry
        # or re-entry right survives until the configured post-start deadline.
        if tournament.get("status") == "running":
            tournament["reentry_grace_until_epoch"] = deadline
            state["session_active"] = False
            state["next_hand_at_epoch"] = deadline

    runtime_cls.finish = finish
    sitngo_runtime._JJ_ENTRY_FINISH_GUARD_INSTALLED = True


__all__ = ["install"]
