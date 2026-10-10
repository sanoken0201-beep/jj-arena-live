"""Non-destructive phase-two season metadata and draft management regression."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


def run():
    folder=Path(tempfile.mkdtemp(prefix="jj-seasons-p2-"))
    os.environ.pop("DATABASE_URL",None)
    os.environ["JJ_DB_PATH"]=str(folder/"seasons.sqlite3")
    os.environ["JJ_ENABLE_DEMO_MEMBER"]="0"
    os.environ["JJ_ADMIN_NAME"]="シーズンカンリ"
    os.environ["JJ_ADMIN_PIN"]="654321"
    os.environ["RENDER"]="1"

    from build_served_assets import main as build_assets
    build_assets()
    import app as production
    import season_management
    import admin_console

    with (
        TestClient(production.app,base_url="https://testserver",raise_server_exceptions=False) as admin,
        TestClient(production.app,base_url="https://testserver",raise_server_exceptions=False) as member,
    ):
        login=admin.post("/api/auth/pin",json={"name":"シーズンカンリ","pin":"654321"})
        assert login.status_code==200,login.text
        member_login=member.post("/api/auth/pin",json={"name":"シーズンメンバー","pin":"112233"})
        assert member_login.status_code==200,member_login.text
        assert member.get("/api/admin/console/seasons").status_code==403
        assert member.post("/api/admin/console/seasons",json={
            "name":"unauthorized","start_date":"2027-04-01","end_exclusive":"2027-10-01"
        }).status_code==403
        assert admin.get("/admin-static/admin_seasons.js").status_code==200

        before=admin.get("/api/rankings",params={"season":"fall"})
        assert before.status_code==200,before.text
        before_month=admin.get("/api/rankings",params={"season":"fall","month":"2026-10"}).json()
        summer=admin.get("/api/rankings",params={"season":"summer"}).json()

        seasons=admin.get("/api/admin/console/seasons")
        assert seasons.status_code==200,seasons.text
        items={s["season_id"]:s for s in seasons.json()}
        assert set(items)=={"summer","fall"},items
        assert (items["summer"]["start_date"],items["summer"]["end_exclusive"])==("0000-01-01","2026-09-01")
        assert (items["fall"]["start_date"],items["fall"]["end_exclusive"])==("2026-09-01","2027-04-01")
        assert items["fall"]["name"]=="JJ 2026 Winter Season"
        assert items["fall"]["locked_bounds"]==1
        assert items["fall"]["status"]=="active"

        renamed=admin.patch("/api/admin/console/seasons/fall",json={
            "name":"JJ 2026/27 Winter Season"
        })
        assert renamed.status_code==200,renamed.text
        assert renamed.json()["name"]=="JJ 2026/27 Winter Season"
        assert admin.get("/api/seasons").status_code==200
        public=member.get("/api/seasons").json()
        assert [s["season_id"] for s in public]==["fall","summer"],public
        assert public[0]["name"]=="JJ 2026/27 Winter Season"

        restricted=admin.patch("/api/admin/console/seasons/fall",json={
            "start_date":"2026-09-02"
        })
        assert restricted.status_code==409,restricted.text
        assert admin.patch("/api/admin/console/seasons/summer",json={
            "end_exclusive":"2026-08-30"
        }).status_code==409
        assert admin.patch("/api/admin/console/seasons/fall",json={
            "status":"archived"
        }).status_code==422

        draft_input={
            "name":"JJ 2027 Spring Season",
            "start_date":"2027-04-01",
            "end_exclusive":"2027-10-01",
        }
        assert admin.post("/api/admin/console/seasons",json={
            **draft_input,"start_date":"2027-03-10"
        }).status_code==409
        assert admin.post("/api/admin/console/seasons",json={
            **draft_input,"start_date":"2027-02-29"
        }).status_code==400
        assert admin.post("/api/admin/console/seasons",json={
            **draft_input,"end_exclusive":"2027-04-01"
        }).status_code==400
        assert admin.post("/api/admin/console/seasons",json={
            **draft_input,"status":"active"
        }).status_code==422

        created=admin.post("/api/admin/console/seasons",json=draft_input)
        assert created.status_code==201,created.text
        ident=created.json()["season_id"]
        assert ident.startswith("season-")
        assert created.json()["status"]=="draft"
        assert created.json()["locked_bounds"]==0
        assert len(admin.get("/api/admin/console/seasons").json())==3
        assert len(member.get("/api/seasons").json())==2,"Draft leaked to players"
        assert admin.post("/api/admin/console/seasons",json={
            **draft_input,"name":"overlap","start_date":"2027-09-01"
        }).status_code==409
        updated=admin.patch("/api/admin/console/seasons/"+ident,json={
            "name":"JJ 2027 Spring & Summer Season",
            "end_exclusive":"2027-10-15",
        })
        assert updated.status_code==200,updated.text
        assert updated.json()["name"]=="JJ 2027 Spring & Summer Season"
        assert updated.json()["end_exclusive"]=="2027-10-15"
        assert admin.patch("/api/admin/console/seasons/not-found",json={
            "name":"missing"
        }).status_code==404

        audit_before=admin.get("/api/admin/console/audit").json()
        with patch.object(admin_console,"_audit",side_effect=RuntimeError("audit fail")):
            failed=admin.patch("/api/admin/console/seasons/"+ident,json={
                "name":"SHOULD NOT COMMIT"
            })
            assert failed.status_code==500,failed.text
        after_fail=next(x for x in admin.get("/api/admin/console/seasons").json()
                        if x["season_id"]==ident)
        assert after_fail["name"]=="JJ 2027 Spring & Summer Season"
        assert len(admin.get("/api/admin/console/audit").json())==len(audit_before)
        record=admin.get("/api/admin/console/audit").json()
        season_actions=[x for x in record if x["action"].startswith("season.")]
        assert len(season_actions)==3,[x["action"] for x in season_actions]
        assert [x["action"] for x in season_actions]==[
            "season.update","season.create","season.update"
        ]

        # Repeated deployments must never replace edited labels or add duplicates.
        season_management._init(production.db,production.runtime_server)
        assert len(admin.get("/api/admin/console/seasons").json())==3
        assert next(x for x in member.get("/api/seasons").json()
                    if x["season_id"]=="fall")["name"]=="JJ 2026/27 Winter Season"

        assert admin.get("/api/rankings",params={"season":"fall"}).json()==before.json()
        assert admin.get("/api/rankings",params={
            "season":"fall","month":"2026-10"
        }).json()==before_month
        assert admin.get("/api/rankings",params={"season":"summer"}).json()==summer
        with production.db.connect() as con:
            columns={row["name"] for row in con.execute("PRAGMA table_info(jj_seasons)")}
            assert {"season_id","name","start_date","end_exclusive","status","locked_bounds"} <= columns
            assert con.execute("SELECT COUNT(*) n FROM jj_seasons").fetchone()["n"]==3
    print("JJ_SEASON_MANAGEMENT_PHASE2_OK archival metadata, validation, auth, audit, restart, rankings")


if __name__=="__main__":
    run()
