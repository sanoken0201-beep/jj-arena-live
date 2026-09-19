from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

# The release gate deliberately strips production secrets. Create a cheap local
# administrator before importing the production entrypoint so this test remains
# isolated from production and fast in CI/Render builds.
os.environ.setdefault("JJ_ADMIN_NAME", "シットゴーテスト")
os.environ["JJ_ADMIN_PIN"] = "123456"
os.environ["JJ_PBKDF2_ROUNDS"] = "1000"

from fastapi import HTTPException

import app as production_app
import sitngo


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def add_member(index: int) -> int:
    db = production_app.db
    name = f"テストプレイヤー{index}"
    with db.connect() as con:
        return db.insert_returning_id(
            con,
            "INSERT INTO users(name,email,password_hash,role,arena_chips,xp,approved,disabled,ranking_name,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                name,
                f"sitngo-test-{index}@jj.invalid",
                db.hash_password("111111"),
                "member",
                0,
                0,
                1,
                0,
                name,
                db.utcnow(),
            ),
        )


def main() -> None:
    app = production_app.app
    db = production_app.db
    service = getattr(app.state, "jj_sitngo", None)
    require(service is not None, "Sit&Go service was not installed on production app")

    route_contract = {(getattr(r, "path", ""), tuple(sorted(getattr(r, "methods", None) or ()))) for r in app.router.routes}
    require(("/api/sitngo/next", ("GET",)) in route_contract, "player Sit&Go route missing")
    require(("/api/admin/sitngo", ("GET",)) in route_contract, "admin Sit&Go list route missing")
    require(("/api/admin/sitngo", ("POST",)) in route_contract, "admin Sit&Go create route missing")

    levels = sitngo.BLIND_STRUCTURE
    require(len(levels) == 15, "prepared Sit&Go structure must contain 150 minutes")
    require(all(int(x["minutes"]) == 10 for x in levels), "all Sit&Go levels must be 10 minutes")
    require(all(int(x["big_blind"]) == int(x["bb_ante"]) for x in levels), "BB ante must equal BB")
    require(
        all(int(x[k]) % 100 == 0 for x in levels for k in ("small_blind", "big_blind", "bb_ante")),
        "Sit&Go chips/blinds must remain in 100-point units",
    )
    require(levels[8]["level"] == 9, "90-minute target must align with level 9")

    with db.connect() as con:
        admin = con.execute("SELECT id FROM users WHERE role='admin' ORDER BY id LIMIT 1").fetchone()
    require(admin is not None, "isolated test admin was not created")
    admin_id = int(admin["id"])
    members = [add_member(i) for i in range(1, 8)]

    # Use a fixed daytime UTC instant so this registration-window regression is\n    # deterministic and cannot cross the JST midnight floor used by\n    # _registration_open_for(). Product behavior is unchanged; only the test\n    # clock is pinned away from the date-boundary edge case.\n    now = datetime(2026, 9, 15, 3, 0, tzinfo=timezone.utc)  # 12:00 JST\n    sitngo._utcnow = lambda: now\n    starts = now + timedelta(minutes=30)\n    event = service.create_event(
        sitngo.SitNGoCreateIn(name="JJ Sit&Go Phase 1", starts_at=starts.isoformat()),
        admin_id,
    )
    require(event["max_players"] == 6 and event["min_players"] == 2, "6-max/minimum-player contract drift")
    require(event["starting_stack"] == 10_000, "starting stack must be 10,000")
    require(datetime.fromisoformat(event["registration_opens_at"]) <= now, "30-minute-away event should already be open")

    for order, uid in enumerate(members[:6], start=1):
        registered = service.register(event["id"], uid)
        require(registered["is_registered"], f"member {uid} registration not persisted")
        require(registered["registration_order"] == order, "registration must remain first-come-first-served")
    full = service._event_payload(service._row(event["id"]), members[0])
    require(full["participant_count"] == 6 and full["full"], "event must close at six registrations")
    try:
        service.register(event["id"], members[6])
    except HTTPException as exc:
        require(exc.status_code == 409, "seventh registration should be a conflict/full response")
    else:
        raise AssertionError("seventh registration was incorrectly accepted")

    cancelled = service.cancel_registration(event["id"], members[2])
    require(cancelled["participant_count"] == 5, "registration cancellation did not reopen one seat")
    replacement = service.register(event["id"], members[6])
    require(replacement["registration_order"] == 6, "replacement registration should become sixth active entrant")

    service.reconcile(starts + timedelta(seconds=1))
    running = service._event_payload(service._row(event["id"]), members[0], admin=True)
    require(running["status"] == "running", "2-6 entrants must auto-start at scheduled time")
    active = [p for p in running["participants"] if p["status"] == "active"]
    seats = [int(p["seat"]) for p in active]
    require(len(active) == 6, "all registered entrants must become active at start")
    require(len(set(seats)) == 6 and all(0 <= seat <= 5 for seat in seats), "random seats must be unique 6-max seats")

    short_start = now + timedelta(minutes=40)
    short = service.create_event(
        sitngo.SitNGoCreateIn(name="Minimum players check", starts_at=short_start.isoformat()),
        admin_id,
    )
    service.register(short["id"], members[0])
    service.reconcile(short_start + timedelta(seconds=1))
    short_row = service._row(short["id"])
    require(short_row["status"] == "cancelled", "one-player event must auto-cancel at start")
    require(short_row["cancel_reason"] == "minimum_players_not_met", "auto-cancel reason drift")

    editable_start = now + timedelta(hours=2)
    editable = service.create_event(
        sitngo.SitNGoCreateIn(name="Editable", starts_at=editable_start.isoformat()),
        admin_id,
    )
    moved = editable_start + timedelta(minutes=20)
    edited = service.update_event(
        editable["id"],
        sitngo.SitNGoUpdateIn(name="Edited Sit&Go", starts_at=moved.isoformat()),
        admin_id,
    )
    require(edited["name"] == "Edited Sit&Go", "admin rename failed")
    require(abs((datetime.fromisoformat(edited["starts_at"]) - moved).total_seconds()) < 1, "admin reschedule failed")
    stopped = service.cancel_event(editable["id"], "test cancellation", admin_id)
    require(stopped["status"] == "cancelled", "admin cancellation failed")

    index = production_app._patched_index()
    js = production_app._patched_app_js()
    css = production_app._patched_styles()
    require('id="sitngoPanel"' in index and 'data-play-mode="sitngo"' in index, "player Sit&Go panel missing")
    require(sitngo_ui_marker() in js, "player Sit&Go JavaScript marker missing")
    require(sitngo_ui_marker() in css, "player Sit&Go CSS marker missing")

    print("JJ_SITNGO_PHASE1_OK")


def sitngo_ui_marker() -> str:
    # Keep the test independent from implementation details beyond the stable marker.
    return "jj sitngo phase1 ui 2026-09-15"


if __name__ == "__main__":
    main()
