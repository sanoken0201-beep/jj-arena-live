"""Regression for permanent bans."""
import os
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient

def run():
    path=Path(tempfile.mkdtemp(prefix="jj-ban-")) / "test.db"
    os.environ.pop("DATABASE_URL", None)
    os.environ["JJ_DB_PATH"]=str(path)
    os.environ["RENDER"]="1"
    os.environ["JJ_ENABLE_DEMO_MEMBER"]="0"
    os.environ["JJ_ADMIN_NAME"]="テストカンリ"
    os.environ["JJ_ADMIN_PIN"]="654321"
    import app
    with TestClient(app.app,base_url="https://testserver") as admin, TestClient(app.app,base_url="https://testserver") as member:
        r=member.post("/api/auth/pin",json={"name":"バンテスト","pin":"123456"})
        assert r.status_code==200,r.text
        uid=r.json()["user"]["id"]
        assert admin.post("/api/auth/pin",json={"name":"テストカンリ","pin":"654321"}).status_code==200
        assert admin.post(f"/api/admin/console/users/{uid}/permanent-ban",json={"reason":"運営規則への違反"}).status_code==200
        assert member.get("/api/me").status_code in (401,403)
        assert admin.patch(f"/api/admin/console/users/{uid}",json={"disabled":False}).status_code==409
        assert admin.delete(f"/api/admin/console/users/{uid}").status_code==200
        assert member.post("/api/auth/pin",json={"name":"バン・テスト","pin":"111111"}).status_code==403
        bans=admin.get("/api/admin/console/permanent-bans").json()
        assert bans and bans[0]["user_id"]==uid
        bid=bans[0]["id"]
        assert admin.post(f"/api/admin/console/permanent-bans/{bid}/lift",json={"reason":"誤認のため解除"}).status_code==200
        r=member.post("/api/auth/pin",json={"name":"バンテスト","pin":"111111"})
        assert r.status_code==200,r.text
        assert r.json()["user"]["id"]!=uid
    print("JJ_PERMANENT_BAN_OK")

if __name__=="__main__":
    run()
