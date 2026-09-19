"""Regression coverage for transactional Sit&Go point integration."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch
import uuid

from fastapi import HTTPException

import sitngo_points
from smoke_test_sitngo_phase1 import add_member, production_app, registration_moment, sitngo


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def seed_points(uid: int, amount: int, admin_id: int) -> None:
    db = production_app.db
    stamp = db.utcnow()
    with db.connect() as con:
        con.execute(
            """INSERT INTO point_ledger(
                   id,user_id,amount,kind,reason,effective_at,created_by,created_at,reversal_of
               ) VALUES (?,?,?,?,?,?,?,?,NULL)""",
            (
                "pt-test-" + uuid.uuid4().hex,
                uid,
                amount,
                "credit",
                "Sit&Go point regression seed",
                stamp,
                admin_id,
                stamp,
            ),
        )


def balance(uid: int) -> Decimal:
    service = production_app.app.state.jj_sitngo
    with production_app.db.connect() as con:
        return sitngo_points.official_balance(
            con,
            production_app.db,
            service.runtime.server,
            uid,
        )


def create_event(service, admin_id: int, name: str, starts: datetime, fee: int):
    return service.create_event(
        sitngo.SitNGoCreateIn(
            name=name,
            starts_at=starts.isoformat(),
            entry_fee_points=fee,
        ),
        admin_id,
    )


def register_at_window(service, event: dict, uid: int):
    with patch.object(sitngo, "_utcnow", return_value=registration_moment(event)):
        return service.register(event["id"], uid)


def finish_with_results(runtime, eid: str, ordered_results: list[tuple[int, int]]) -> None:
    state = runtime.load(eid)
    names = {int(p["user_id"]): p["name"] for p in state["seats"]}
    state["status"] = "waiting"
    state["session_active"] = False
    state["next_hand_at_epoch"] = None
    state["tournament"]["results"] = [
        {
            "user_id": uid,
            "name": names[uid],
            "place": place,
            "hand_no": int(state.get("hand_no") or 1),
            "starting_stack": 0,
            "prize_points": 0,
        }
        for uid, place in ordered_results
    ]
    state["tournament"]["status"] = "finished"
    state["tournament"]["finished_at"] = production_app.db.utcnow()
    runtime.save(state)


def main() -> None:
    db = production_app.db
    service = production_app.app.state.jj_sitngo
    runtime = service.runtime
    with db.connect() as con:
        con.execute("UPDATE sitngo_events SET status='finished',updated_at=? WHERE status='running'", (db.utcnow(),))
        admin = con.execute("SELECT id FROM users WHERE role='admin' ORDER BY id LIMIT 1").fetchone()
    require(admin is not None, "admin missing")
    admin_id = int(admin["id"])

    users = [add_member(9100 + i) for i in range(12)]
    for uid in users:
        seed_points(uid, 2_000, admin_id)
    poor = add_member(9199)
    seed_points(poor, 300, admin_id)

    now = datetime.now(timezone.utc)

    # Insufficient balance is fail-closed before registration or debit.
    event = create_event(service, admin_id, "Insufficient", now + timedelta(minutes=20), 400)
    with patch.object(sitngo, "_utcnow", return_value=registration_moment(event)):
        payload = service._event_payload(service._row(event["id"]), poor)
        require(payload["point_balance"] == 300.0, "player point balance missing")
        require(not payload["can_register"], "insufficient balance incorrectly allowed registration")
        require(payload["registration_block_reason"] == "insufficient_points", "wrong point block reason")
        try:
            service.register(event["id"], poor)
        except HTTPException as exc:
            require(exc.status_code == 409, "insufficient points should be a conflict")
        else:
            raise AssertionError("insufficient balance registration succeeded")
    with db.connect() as con:
        n = con.execute(
            "SELECT COUNT(*) n FROM point_ledger WHERE user_id=? AND kind=?",
            (poor, sitngo_points.ENTRY_KIND),
        ).fetchone()
    require(int(n["n"] or 0) == 0, "failed registration created a debit")
    service.cancel_event(event["id"], "test cleanup", admin_id)

    # Registration, cancellation refund and re-registration are exact per cycle.
    event = create_event(service, admin_id, "Cycle", now + timedelta(minutes=30), 400)
    before = balance(users[0])
    register_at_window(service, event, users[0])
    require(balance(users[0]) == before - Decimal("400.00"), "entry debit missing")
    with patch.object(sitngo, "_utcnow", return_value=registration_moment(event) + timedelta(seconds=5)):
        service.cancel_registration(event["id"], users[0])
    require(balance(users[0]) == before, "registration cancellation did not refund")
    register_at_window(service, event, users[0])
    require(balance(users[0]) == before - Decimal("400.00"), "re-registration did not create a new debit")
    with db.connect() as con:
        cycles = con.execute(
            "SELECT cycle,refund_tx_id FROM sitngo_point_entries WHERE event_id=? AND user_id=? ORDER BY cycle",
            (event["id"], users[0]),
        ).fetchall()
    require(len(cycles) == 2 and cycles[0]["refund_tx_id"] and not cycles[1]["refund_tx_id"], "registration cycles are not auditable")

    # Entry fee becomes immutable once an event has any registration history.
    try:
        service.update_event(
            event["id"],
            sitngo.SitNGoUpdateIn(entry_fee_points=500),
            admin_id,
        )
    except HTTPException as exc:
        require(exc.status_code == 409, "entry fee edit after registration must be rejected")
    else:
        raise AssertionError("entry fee changed after registration history")

    # The same account cannot reserve two Sit&Go events concurrently.
    other = create_event(service, admin_id, "Other", now + timedelta(minutes=35), 400)
    with patch.object(sitngo, "_utcnow", return_value=registration_moment(other)):
        try:
            service.register(other["id"], users[0])
        except HTTPException as exc:
            require(exc.status_code == 409, "parallel Sit&Go registration must be rejected")
        else:
            raise AssertionError("same account registered into two active Sit&Go events")
    service.cancel_event(event["id"], "cycle cleanup", admin_id)
    require(balance(users[0]) == before, "admin cancellation did not refund active entry")
    service.cancel_event(other["id"], "other cleanup", admin_id)

    # Automatic cancellation for too few players also refunds the debit.
    auto = create_event(service, admin_id, "Auto refund", now + timedelta(minutes=45), 400)
    before_auto = balance(users[1])
    register_at_window(service, auto, users[1])
    service.reconcile(datetime.fromisoformat(auto["starts_at"]) + timedelta(seconds=1))
    require(service._row(auto["id"])["status"] == "cancelled", "one-player event did not cancel")
    require(balance(users[1]) == before_auto, "auto-cancel did not refund entry")

    # <=5 entrants: the full pool goes to first place, exactly once.
    three = create_event(service, admin_id, "Three player payout", now + timedelta(minutes=55), 400)
    three_users = users[2:5]
    three_before = {uid: balance(uid) for uid in three_users}
    with patch.object(sitngo, "_utcnow", return_value=registration_moment(three)):
        for uid in three_users:
            service.register(three["id"], uid)
    service.reconcile(datetime.fromisoformat(three["starts_at"]) + timedelta(seconds=1))
    finish_with_results(runtime, three["id"], [(three_users[0], 1), (three_users[1], 2), (three_users[2], 3)])
    require(balance(three_users[0]) == three_before[three_users[0]] + Decimal("800.00"), "winner-take-all net balance incorrect")
    require(balance(three_users[1]) == three_before[three_users[1]] - Decimal("400.00"), "runner-up should receive no <=5 payout")
    summary = service._event_payload(service._row(three["id"]), admin_id, admin=True)["point_summary"]
    require(summary["settled"] and summary["pool_points"] == 1200.0, "three-player settlement summary incorrect")
    with db.connect() as con:
        prizes_before = int(con.execute(
            "SELECT COUNT(*) n FROM point_ledger WHERE kind=? AND reason LIKE ?",
            (sitngo_points.PRIZE_KIND, "%Three player payout%"),
        ).fetchone()["n"] or 0)
    runtime.save(runtime.load(three["id"]))
    with db.connect() as con:
        prizes_after = int(con.execute(
            "SELECT COUNT(*) n FROM point_ledger WHERE kind=? AND reason LIKE ?",
            (sitngo_points.PRIZE_KIND, "%Three player payout%"),
        ).fetchone()["n"] or 0)
    require(prizes_before == prizes_after == 1, "finished event paid prize more than once")

    # Six entrants: 1st gets 70%, second prize is the full residual. A tie for
    # second occupies places 2 and 3, so that residual prize is split equally.
    six = create_event(service, admin_id, "Six player tie payout", now + timedelta(minutes=70), 400)
    six_users = users[5:11]
    six_before = {uid: balance(uid) for uid in six_users}
    with patch.object(sitngo, "_utcnow", return_value=registration_moment(six)):
        for uid in six_users:
            service.register(six["id"], uid)
    service.reconcile(datetime.fromisoformat(six["starts_at"]) + timedelta(seconds=1))
    results = [
        (six_users[0], 1),
        (six_users[1], 2),
        (six_users[2], 2),
        (six_users[3], 4),
        (six_users[4], 5),
        (six_users[5], 6),
    ]
    finish_with_results(runtime, six["id"], results)
    # Pool 2400: first 1680, residual 720 split across tied second = 360 each.
    require(balance(six_users[0]) == six_before[six_users[0]] + Decimal("1280.00"), "six-player first prize incorrect")
    require(balance(six_users[1]) == six_before[six_users[1]] - Decimal("40.00"), "tied second net payout incorrect")
    require(balance(six_users[2]) == six_before[six_users[2]] - Decimal("40.00"), "second tied player net payout incorrect")
    for uid in six_users[3:]:
        require(balance(uid) == six_before[uid] - Decimal("400.00"), "unpaid six-player finisher received points")
    six_payload = service._event_payload(service._row(six["id"]), admin_id, admin=True)
    payouts = {int(x["user_id"]): float(x["amount"]) for x in six_payload["point_summary"]["payouts"]}
    require(payouts == {six_users[0]: 1680.0, six_users[1]: 360.0, six_users[2]: 360.0}, f"unexpected six-player payouts: {payouts}")
    require(abs(sum(payouts.values()) - 2400.0) < 0.001, "six-player payout did not conserve pool")

    # Ledger kinds stay separate from reversible manual adjustments.
    with db.connect() as con:
        kinds = {
            str(row["kind"])
            for row in con.execute(
                "SELECT DISTINCT kind FROM point_ledger WHERE kind LIKE 'sitngo_%'"
            ).fetchall()
        }
    require(
        {sitngo_points.ENTRY_KIND, sitngo_points.REFUND_KIND, sitngo_points.PRIZE_KIND}.issubset(kinds),
        f"Sit&Go ledger kinds missing: {kinds}",
    )

    print("JJ_SITNGO_POINTS_OK")


if __name__ == "__main__":
    main()
