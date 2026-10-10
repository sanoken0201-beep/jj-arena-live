"""Rollover regression: archive history, reset *view*, refuse premature transitions."""
from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


def main() -> None:
    folder = Path(tempfile.mkdtemp(prefix="jj-rollover-"))
    os.environ.pop("DATABASE_URL", None)
    os.environ["JJ_DB_PATH"] = str(folder / "test.sqlite3")
    os.environ["JJ_ADMIN_NAME"] = "キカンカンリ"
    os.environ["JJ_ADMIN_PIN"] = "654321"
    os.environ["JJ_ENABLE_DEMO_MEMBER"] = "0"
    os.environ["RENDER"] = "1"

    from build_served_assets import main as build_assets
    build_assets()
    import app as production
    import season_management
    import season_rollover

    with TestClient(production.app, base_url="https://testserver",
                    raise_server_exceptions=False) as admin, \
         TestClient(production.app, base_url="https://testserver",
                    raise_server_exceptions=False) as member:
        a = admin.post("/api/auth/pin", json={
            "name":"キカンカンリ", "pin":"654321"
        })
        assert a.status_code == 200, a.text
        m = member.post("/api/auth/pin", json={
            "name":"キカンメンバー", "pin":"123456"
        })
        assert m.status_code == 200, m.text
        member_id = int(m.json()["user"]["id"])

        # Hand results / club entries / quiz and manual ledger rows from the
        # old season will remain in their original immutable source tables.
        with production.db.connect() as con:
            con.execute(
                "INSERT INTO entries(id,date,name,remaining,reentries,initial,points,"
                "game,game_type,source,created_by,created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                ("winter-sample","2026-10-09T12:00","キカンメンバー",
                 600,0,450,150,"ring","ring","test",int(a.json()["user"]["id"]),
                 "2026-10-09T12:00:00"),
            )
            con.execute(
                "INSERT INTO point_ledger(id,user_id,amount,kind,reason,effective_at,"
                "created_by,created_at) VALUES (?,?,?,?,?,?,?,?)",
                ("winter-quiz",member_id,10,"quiz_reward","test",
                 "2026-10-09T12:00:00",member_id,"2026-10-09T12:00:00"),
            )
        before = admin.get("/api/rankings").json()
        assert next(x for x in before if x["name"]=="キカンメンバー")["points"]==160
        old_entries=admin.get("/api/entries").json()
        assert any(x["id"]=="winter-sample" for x in old_entries)
        assert admin.get("/api/home/core").status_code==200

        payload={"name":"JJ 2027 Spring Season","start_date":"2027-04-01",
                 "end_exclusive":"2027-09-01"}
        response=admin.post("/api/admin/console/seasons",json=payload)
        assert response.status_code==201,response.text
        season_id=response.json()["season_id"]
        endpoint="/api/admin/console/seasons/"+season_id+"/activate"
        body={"expected_current_season_id":"fall","current_pin":"654321",
              "confirmation":"START NEW SEASON"}
        assert member.post(endpoint,json=body).status_code==403
        assert admin.post(endpoint,json={**body,"confirmation":"invalid"}).status_code==422
        assert admin.post(endpoint,json={**body,"current_pin":"000000"}).status_code==403
        assert admin.get("/api/season/current").json()["season_id"]=="fall"

        # A pending future season may not be started in October 2026.
        with patch.object(season_rollover,"today_jst",return_value="2026-10-10"):
            early=admin.post(endpoint,json=body)
            assert early.status_code==409,early.text
        assert admin.get("/api/rankings").json()==before

        # Invalid sequentiality and concurrent game safety both fail closed.
        with patch.object(season_rollover,"today_jst",return_value="2027-04-01"):
            with patch.object(season_rollover,"_check_live_games",
                              side_effect=__import__("fastapi").HTTPException(
                                  409,"a tournament is still running")):
                busy=admin.post(endpoint,json=body)
                assert busy.status_code==409,busy.text
            active=admin.post(endpoint,json=body)
        assert active.status_code==200,active.text
        assert active.json()["current"]["season_id"]==season_id
        assert active.json()["archived_season_id"]=="fall"
        assert admin.post(endpoint,json=body).status_code==409

        assert admin.get("/api/season/current").json()["season_id"]==season_id
        public=member.get("/api/seasons").json()
        assert [x["season_id"] for x in public][:2]==[season_id,"fall"],public
        assert public[1]["status"]=="archived"

        # Legacy 'fall' clients now receive ACTIVE points, but explicit
        # 'archive:fall' still returns every historical winter component.
        assert admin.get("/api/rankings").json()==[]
        assert admin.get("/api/rankings",params={"season":"fall"}).json()==[]
        archived=admin.get("/api/rankings",params={"season":"archive:fall"})
        assert archived.status_code==200,archived.text
        assert archived.json()[0]["points"]==160
        assert admin.get("/api/rankings",params={
            "season":season_id
        }).json()==[]
        assert admin.get("/api/rankings",params={
            "season":season_id,"month":"2027-04"
        }).json()==[]
        assert admin.get("/api/home/core").json()["rankings"]==[]
        assert admin.get("/api/entries").json()==[]
        assert any(x["id"]=="winter-sample" for x in
                   admin.get("/api/entries",params={"archive":True}).json())
        assert admin.get("/api/admin/console/settings").json()[
            "season_start"]=="2027-04-01"
        overview=admin.get("/api/admin/console/overview").json()
        assert overview["season"]["start"]=="2027-04-01"
        assert overview["ranking_total"]==0
        users=admin.get("/api/admin/console/users").json()
        assert next(x for x in users if x["id"]==member_id)["season_points"]==0

        # An actual new club event and a Sit&Go settlement belong only to the
        # fresh window. The previous archive must remain identical.
        with production.db.connect() as con:
            con.execute(
                "INSERT INTO entries(id,date,name,remaining,reentries,initial,points,"
                "game,game_type,source,created_by,created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                ("spring-sample","2027-04-03T12:00","キカンメンバー",
                 500,0,450,50,"ring","ring","test",int(a.json()["user"]["id"]),
                 "2027-04-03T12:00:00"),
            )
            con.execute(
                "INSERT INTO point_ledger(id,user_id,amount,kind,reason,effective_at,"
                "created_by,created_at) VALUES (?,?,?,?,?,?,?,?)",
                ("spring-sng",member_id,20,"sitngo_prize","test",
                 "2027-04-03T12:00:00",member_id,"2027-04-03T12:00:00"),
            )
        now=admin.get("/api/rankings").json()
        assert next(x for x in now if x["name"]=="キカンメンバー")["points"]==70,now
        assert admin.get("/api/rankings",params={"season":"archive:fall"}).json()==archived.json()
        assert admin.get("/api/home/core").json()["rankings"]==now
        assert [x["id"] for x in admin.get("/api/entries").json()]==["spring-sample"]
        assert len([x for x in admin.get("/api/admin/console/audit").json()
                    if x["action"]=="season.activate"])==1

        # Restarted app bootstrap cannot resurrect archived legacy 'fall'.
        season_management._init(production.db, production.runtime_server)
        assert season_management.active_season(production.db)["season_id"]==season_id
        with production.db.connect() as con:
            assert con.execute("SELECT COUNT(*) n FROM entries").fetchone()["n"]==2
            assert con.execute("SELECT COUNT(*) n FROM point_ledger").fetchone()["n"]==2
    print("JJ_SEASON_ROLLOVER_OK future guard, PIN, archive, zero, club, SNG, UI endpoints")


if __name__=="__main__":
    main()
