from __future__ import annotations

import os
import sys
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import HTTPException

from runtime_builder import build_runtime


def _route(app, path: str, method: str):
    for route in app.router.routes:
        if getattr(route, "path", None) == path and method.upper() in (getattr(route, "methods", None) or set()):
            return route.endpoint
    raise AssertionError(f"route missing: {method} {path}")


def _clear_modules() -> dict[str, object]:
    names = ["db", "server", "poker_engine"]
    old: dict[str, object] = {}
    for name in names:
        if name in sys.modules:
            old[name] = sys.modules.pop(name)
    return old


def _iso(days_ago: int = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def _insert_hand(con, *, hand_id: str, uid: int, name: str, completed_at: str, partial: int = 0,
                 position: str = "BTN", net_bb: float = 0.0, vpip: int = 0, pfr: int = 0,
                 three_bet_opp: int = 0, three_bet: int = 0, faced_three_bet: int = 0,
                 folded_to_three_bet: int = 0, cbet_opp: int = 0, cbet: int = 0,
                 timeout_count: int = 0, hand_no: int = 1) -> None:
    con.execute(
        """INSERT INTO jj_hand_history(
             hand_id,table_id,table_name,hand_no,started_at,completed_at,small_blind,big_blind,
             button_seat,player_count,reached_street,showdown,partial_capture
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (hand_id, "focus-table", "Focus Table", hand_no, completed_at, completed_at, 50, 100,
         0, 2, "flop", 0, partial),
    )
    con.execute(
        """INSERT INTO jj_hand_players(
             hand_id,user_id,player_name,seat,position,starting_stack_bb,effective_stack_bb,net_bb,
             vpip,pfr,three_bet_opp,three_bet,faced_three_bet,folded_to_three_bet,cbet_opp,cbet,timeout_count
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (hand_id, uid, name, 0, position, 100.0, 100.0, net_bb, vpip, pfr,
         three_bet_opp, three_bet, faced_three_bet, folded_to_three_bet, cbet_opp, cbet, timeout_count),
    )


def main() -> None:
    postgres = "--postgres" in sys.argv
    work = Path(tempfile.mkdtemp(prefix="jj-v1244-focus-"))
    runtime = build_runtime(work / "runtime")
    previous = {k: os.environ.get(k) for k in ("DATABASE_URL", "JJ_DB_PATH", "JJ_ADMIN_NAME", "JJ_ADMIN_PIN", "JJ_ENABLE_DEMO_MEMBER")}
    old_modules = _clear_modules()
    if not postgres:
        os.environ.pop("DATABASE_URL", None)
        os.environ["JJ_DB_PATH"] = str(work / "focus.sqlite3")
    elif not os.environ.get("DATABASE_URL"):
        raise AssertionError("--postgres requires DATABASE_URL")
    os.environ["JJ_ADMIN_NAME"] = "FOCUS_ADMIN"
    os.environ["JJ_ADMIN_PIN"] = "654321"
    os.environ["JJ_ENABLE_DEMO_MEMBER"] = "0"
    sys.path.insert(0, str(runtime))

    try:
        import db  # type: ignore
        import server  # type: ignore
        import hand_analytics
        import hand_analytics_hardening

        hand_analytics.install(server.app, server, db)
        hand_analytics_hardening.install(hand_analytics, server)

        suffix = uuid.uuid4().hex[:10]
        with db.connect() as con:
            uid = db.insert_returning_id(
                con,
                "INSERT INTO users(name,email,password_hash,role,arena_chips,xp,created_at) VALUES (?,?,?,?,?,?,?)",
                (f"Focus-{suffix}", f"focus-{suffix}@jj.invalid", db.hash_password("123456"), "member", 0, 0, db.utcnow()),
            )
            other = db.insert_returning_id(
                con,
                "INSERT INTO users(name,email,password_hash,role,arena_chips,xp,created_at) VALUES (?,?,?,?,?,?,?)",
                (f"Other-{suffix}", f"other-{suffix}@jj.invalid", db.hash_password("123456"), "member", 0, 0, db.utcnow()),
            )

            # Newest matching denominator row.
            _insert_hand(
                con, hand_id=f"focus-new-{suffix}", uid=uid, name="Focus", completed_at=_iso(0),
                net_bb=-4.5, faced_three_bet=1, folded_to_three_bet=1, vpip=1, pfr=1, hand_no=101,
            )
            # Same user, same metric, but outside a 7-day range.
            _insert_hand(
                con, hand_id=f"focus-old-{suffix}", uid=uid, name="Focus", completed_at=_iso(20),
                net_bb=2.0, faced_three_bet=1, folded_to_three_bet=0, hand_no=102,
            )
            # Partial captures must never enter focus results.
            _insert_hand(
                con, hand_id=f"focus-partial-{suffix}", uid=uid, name="Focus", completed_at=_iso(0), partial=1,
                faced_three_bet=1, folded_to_three_bet=1, hand_no=103,
            )
            # Another user's matching row must never leak.
            _insert_hand(
                con, hand_id=f"focus-other-{suffix}", uid=other, name="Other", completed_at=_iso(0),
                faced_three_bet=1, folded_to_three_bet=1, hand_no=104,
            )
            # Other denominators for the supported metric map.
            _insert_hand(
                con, hand_id=f"focus-3bet-{suffix}", uid=uid, name="Focus", completed_at=_iso(0),
                three_bet_opp=1, three_bet=0, hand_no=105,
            )
            _insert_hand(
                con, hand_id=f"focus-cbet-{suffix}", uid=uid, name="Focus", completed_at=_iso(0),
                cbet_opp=1, cbet=1, hand_no=106,
            )
            _insert_hand(
                con, hand_id=f"focus-gap-{suffix}", uid=uid, name="Focus", completed_at=_iso(0),
                vpip=1, pfr=0, hand_no=107,
            )
            _insert_hand(
                con, hand_id=f"focus-timeout-{suffix}", uid=uid, name="Focus", completed_at=_iso(0),
                timeout_count=2, hand_no=108,
            )

        endpoint = _route(server.app, "/api/analysis/focus-hands", "GET")

        all_rows = endpoint(metric="fold_to_3bet", range="all", limit=12, user={"id": uid})
        ids = [x["hand_id"] for x in all_rows["hands"]]
        assert f"focus-new-{suffix}" in ids
        assert f"focus-old-{suffix}" in ids
        assert f"focus-partial-{suffix}" not in ids
        assert f"focus-other-{suffix}" not in ids
        assert all_rows["count"] == 2, all_rows
        newest = next(x for x in all_rows["hands"] if x["hand_id"] == f"focus-new-{suffix}")
        assert newest["position"] == "BTN"
        assert newest["net_bb"] == -4.5
        assert newest["context"]["faced_three_bet"] is True
        assert newest["context"]["folded_to_three_bet"] is True
        assert "cards" not in newest and "actions" not in newest and "review" not in newest

        seven = endpoint(metric="fold_to_3bet", range="7d", limit=12, user={"id": uid})
        assert [x["hand_id"] for x in seven["hands"]] == [f"focus-new-{suffix}"], seven

        assert endpoint(metric="three_bet", range="all", limit=12, user={"id": uid})["count"] == 1
        assert endpoint(metric="cbet", range="all", limit=12, user={"id": uid})["count"] == 1
        assert endpoint(metric="vpip_pfr_gap", range="all", limit=12, user={"id": uid})["count"] == 1
        assert endpoint(metric="timeout", range="all", limit=12, user={"id": uid})["count"] == 1

        limited = endpoint(metric="fold_to_3bet", range="all", limit=1, user={"id": uid})
        assert limited["count"] == 1 and limited["hands"][0]["hand_id"] == f"focus-new-{suffix}"

        try:
            endpoint(metric="not-supported", range="all", limit=12, user={"id": uid})
        except HTTPException as exc:
            assert exc.status_code == 400
        else:
            raise AssertionError("unsupported metric was accepted")

        print("JJ_V1244_FOCUS_INTEGRATION_OK", "POSTGRES" if postgres else "SQLITE")
    finally:
        if str(runtime) in sys.path:
            sys.path.remove(str(runtime))
        for name in ("db", "server", "poker_engine"):
            sys.modules.pop(name, None)
        sys.modules.update(old_modules)
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


if __name__ == "__main__":
    main()
