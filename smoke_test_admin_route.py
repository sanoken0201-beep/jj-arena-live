from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

WORK = Path(tempfile.mkdtemp(prefix="jj-admin-route-"))
os.environ["JJ_DB_PATH"] = str(WORK / "route.db")
os.environ.pop("DATABASE_URL", None)
os.environ["JJ_ADMIN_NAME"] = "ケンイチロウ"
os.environ["JJ_ADMIN_PIN"] = "123456"
os.environ["JJ_ENABLE_DEMO_MEMBER"] = "0"


def main() -> None:
    from fastapi.testclient import TestClient
    from app import app

    paths = [str(getattr(r, "path", "")) for r in app.router.routes]
    admin_index = min(i for i, p in enumerate(paths) if p in {"/admin", "/admin/"})
    fallback_indexes = [i for i, p in enumerate(paths) if p in {"/{path:path}", "/{full_path:path}"}]
    if fallback_indexes:
        assert admin_index < min(fallback_indexes), (admin_index, fallback_indexes, paths)

    client = TestClient(app)

    page = client.get("/admin", follow_redirects=False)
    assert page.status_code == 200, page.status_code
    assert "Admin Console" in page.text, page.text[:200]

    css = client.get("/admin-static/admin.css", follow_redirects=False)
    assert css.status_code == 200, css.status_code
    assert "--bg:" in css.text and ".sidebar" in css.text

    js = client.get("/admin-static/admin.js", follow_redirects=False)
    assert js.status_code == 200, js.status_code
    assert "loadOverview" in js.text and "admin/console/users" in js.text

    unauth = client.get("/api/admin/console/overview", follow_redirects=False)
    assert unauth.status_code in {401, 403}, (unauth.status_code, unauth.text[:200])
    assert "text/html" not in unauth.headers.get("content-type", "")

    login = client.post("/api/auth/pin", json={"name": "ケンイチロウ", "pin": "123456"})
    assert login.status_code == 200, (login.status_code, login.text[:300])
    user = login.json().get("user") or {}
    assert user.get("role") == "admin", user

    overview = client.get("/api/admin/console/overview")
    assert overview.status_code == 200, (overview.status_code, overview.text[:300])
    data = overview.json()
    assert "accounts" in data and "ledger" in data and "season" in data, data

    users = client.get("/api/admin/console/users")
    assert users.status_code == 200, (users.status_code, users.text[:300])
    assert any(u.get("role") == "admin" for u in users.json())

    print("ADMIN_ROUTE_SMOKE_OK", flush=True)


if __name__ == "__main__":
    try:
        main()
    finally:
        shutil.rmtree(WORK, ignore_errors=True)
