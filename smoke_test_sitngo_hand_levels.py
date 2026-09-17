"""Regression coverage for fixed 12-hand Sit&Go blind levels."""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import sitngo_hand_levels
from smoke_test_sitngo_phase1 import add_member, production_app, registration_moment, sitngo


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    require(sitngo_hand_levels.HANDS_PER_LEVEL == 12, "Sit&Go hand-level constant drift")
    require(sitngo_hand_levels.level_index_for_completed_hands(0, 15) == 0, "hand 1 must use level 1")
    require(sitngo_hand_levels.level_index_for_completed_hands(11, 15) == 0, "hand 12 must still use level 1")
    require(sitngo_hand_levels.level_index_for_completed_hands(12, 15) == 1, "hand 13 must use level 2")
    require(sitngo_hand_levels.level_index_for_completed_hands(24, 15) == 2, "hand 25 must use level 3")
    require(sitngo_hand_levels.level_index_for_completed_hands(9999, 15) == 14, "final level must repeat")

    db = production_app.db
    service = production_app.app.state.jj_sitngo
    runtime = service.runtime
    with db.connect() as con:
        # Tests share a disposable database in CI. Do not let an earlier test's
        # deliberately-open tournament trigger the one-running-Sit&Go guard.
        con.execute("UPDATE sitngo_events SET status='finished',updated_at=? WHERE status='running'", (db.utcnow(),))
        admin = con.execute("SELECT id FROM users WHERE role='admin' ORDER BY id LIMIT 1").fetchone()
    require(admin is not None, "test admin missing")
    admin_id = int(admin["id"])
    # Keep this fixture namespace distinct from freezeout/API tests because the
    # PostgreSQL CI job intentionally reuses one disposable database.
    members = [add_member(5200 + i) for i in range(2)]

    starts = datetime.now(timezone.utc) + timedelta(minutes=30)
    event = service.create_event(
        sitngo.SitNGoCreateIn(name="12-hand progression", starts_at=starts.isoformat()),
        admin_id,
    )
    require(event["level_mode"] == "hands", "scheduled event must advertise hand-count levels")
    require(event["hands_per_level"] == 12, "scheduled event must advertise 12 hands per level")

    with patch.object(sitngo, "_utcnow", return_value=registration_moment(event)):
        for uid in members:
            service.register(event["id"], uid)
    launch_at = starts + timedelta(seconds=1)
    service.reconcile(launch_at)

    state = runtime.load(event["id"])
    tournament = state["tournament"]
    require(tournament["level_mode"] == "hands", "new runtime state must persist hand-count mode")
    require(tournament["hands_per_level"] == 12, "runtime state must persist 12-hand level size")
    require(state["hand_no"] == 1 and tournament["level"] == 1, "first hand must start at level 1")
    require((state["small_blind"], state["big_blind"], tournament["bb_ante"]) == (200, 400, 400), "level 1 blinds drift")

    public = runtime.public(state, members[0])
    require(public["tournament"]["next_level_at"] is None, "hand-count mode must not expose a time deadline")
    require(public["tournament"]["hand_in_level"] == 1, "first hand progress must be 1/12")

    clock = launch_at.timestamp() + 1
    for hand_number in range(1, 13):
        state = runtime.load(event["id"])
        require(state["status"] == "playing", f"hand {hand_number} should be active")
        require(state["hand_no"] == hand_number, f"unexpected hand number before hand {hand_number}")
        require(state["tournament"]["level"] == 1, "time passage must not raise blinds before 12 completed hands")
        require(state["big_blind"] == 400, "level 1 BB changed before the 12-hand boundary")

        hand = state["hand"]
        actor = next(p for p in state["seats"] if p["seat"] == hand["action_seat"])
        with patch("time.time", return_value=clock):
            runtime.engine.apply_action(state, actor["user_id"], "fold")
            runtime.save(state)

        waiting = runtime.load(event["id"])
        require(waiting["status"] == "waiting", "folded heads-up hand should finish immediately")
        # Deliberately insert a one-hour gap after every hand. Blind selection
        # must still depend solely on completed hand count.
        clock += 3600
        with patch("time.time", return_value=clock):
            asyncio.run(runtime.tick(event["id"], now=clock))

        after = runtime.load(event["id"])
        if hand_number < 12:
            require(after["hand_no"] == hand_number + 1, "next hand was not dealt")
            require(after["tournament"]["level"] == 1 and after["big_blind"] == 400, "elapsed hours incorrectly advanced the blind level")
        else:
            require(after["hand_no"] == 13, "13th hand was not dealt at the boundary")
            require(after["tournament"]["level"] == 2, "13th hand must start level 2")
            require((after["small_blind"], after["big_blind"], after["tournament"]["bb_ante"]) == (300, 600, 600), "level 2 blinds/BBA not applied atomically between hands")
            pub = runtime.public(after, members[0])
            require(pub["tournament"]["hand_in_level"] == 1, "level 2 must restart progress at 1/12")
            require(pub["tournament"]["hands_until_level_up"] == 11, "level 2 remaining-hand count drift")

    # Player/admin UI must describe the actual scheduler and must not offer an
    # editable minute duration even though the legacy DB payload keeps minutes.
    player_js = production_app._patched_app_js()
    require("12ハンド" in player_js, "player UI does not expose 12-hand levels")
    require("12 HAND LEVELS" in production_app._patched_index(), "player lobby header still advertises timed levels")
    admin_js = (Path(__file__).resolve().parent / "admin_static" / "admin_sitngo.js").read_text(encoding="utf-8")
    require("12ハンド" in admin_js, "admin UI does not expose fixed 12-hand progression")
    require('value="12ハンド" disabled' in admin_js, "admin UI still permits per-level minute editing")
    admin_index = (Path(__file__).resolve().parent / "admin_static" / "index.html").read_text(encoding="utf-8")
    require(sitngo_hand_levels.ADMIN_CACHE_QUERY in admin_index, "admin Sit&Go cache-buster missing")

    # Leave the shared PostgreSQL CI database ready for the next independent
    # contract test. Production never executes this fixture cleanup.
    with db.connect() as con:
        con.execute(
            "UPDATE sitngo_events SET status='finished',updated_at=? WHERE id=?",
            (db.utcnow(), event["id"]),
        )

    print("JJ_SITNGO_HAND_LEVELS_OK")


if __name__ == "__main__":
    main()
