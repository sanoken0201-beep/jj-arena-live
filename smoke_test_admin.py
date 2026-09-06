from __future__ import annotations

import base64
import hashlib
import io
import os
import shutil
import sys
import tarfile
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORK = Path(tempfile.mkdtemp(prefix="jj-admin-smoke-"))
DB_PATH = WORK / "smoke.db"
os.environ["JJ_DB_PATH"] = str(DB_PATH)
os.environ.pop("DATABASE_URL", None)
os.environ["JJ_ADMIN_NAME"] = "ケンイチロウ"
os.environ["JJ_ADMIN_PIN"] = "123456"
os.environ["JJ_ENABLE_DEMO_MEMBER"] = "1"


def stage(label: str):
    print(f"[SMOKE] {label}", flush=True)


def apply_patches(dest: Path) -> None:
    import v15_patch, v16_patch, v17_patch, v18_patch, v19_patch, v20_patch, v21_patch, v22_patch
    import v23_patch, v24_patch, v25_patch, v26_patch, v27_patch, v28_patch, v29_patch, v30_patch
    import v31_patch, v32_patch, v33_patch, v34_patch

    chain = [
        ("v15", lambda: v15_patch.apply(dest)),
        ("v16", lambda: v16_patch.apply(dest)),
        ("v17", lambda: v17_patch.apply(dest)),
        ("v18", lambda: v18_patch.apply(dest, ROOT / "v18_assets")),
        ("v19", lambda: v19_patch.apply(dest)),
        ("v20", lambda: v20_patch.apply(dest)),
        ("v21", lambda: v21_patch.apply(dest)),
        ("v22", lambda: v22_patch.apply(dest)),
        ("v23", lambda: v23_patch.apply(dest)),
        ("v24", lambda: v24_patch.apply(dest)),
        ("v25", lambda: v25_patch.apply(dest)),
        ("v26", lambda: v26_patch.apply(dest)),
        ("v27", lambda: v27_patch.apply(dest)),
        ("v28", lambda: v28_patch.apply(dest)),
        ("v29", lambda: v29_patch.apply(dest)),
        ("v30", lambda: v30_patch.apply(dest)),
        ("v31", lambda: v31_patch.apply(dest)),
        ("v32", lambda: v32_patch.apply(dest)),
        ("v33", lambda: v33_patch.apply(dest)),
        ("v34", lambda: v34_patch.apply(dest)),
    ]
    for name, fn in chain:
        t = time.time()
        fn()
        stage(f"{name} applied in {time.time()-t:.2f}s")


def main() -> None:
    stage("reconstruct release")
    release = ROOT / "release_v14"
    parts = sorted(release.glob("part*.b64"))
    assert len(parts) == 62, len(parts)
    raw = base64.b64decode("".join(p.read_text(encoding="utf-8").strip() for p in parts), validate=True)
    assert hashlib.sha256(raw).hexdigest() == "3ccb973f9ab146ce1c0d7da598242b0c1521a8ecc85c091caa10c1f1ebc9ddfd"
    dest = WORK / "runtime"
    dest.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        archive.extractall(dest)
    stage("release reconstructed")

    apply_patches(dest)
    stage("patch chain complete")

    sys.path.insert(0, str(dest))
    t = time.time()
    import server  # noqa: E402
    stage(f"server imported in {time.time()-t:.2f}s")
    assert getattr(server.app, "version", None) == "1.18.0", server.app.version

    import db  # noqa: E402
    from admin_console import install_admin_console, _rankings  # noqa: E402

    t = time.time()
    install_admin_console(server.app)
    stage(f"admin console installed in {time.time()-t:.2f}s")

    paths = [getattr(r, "path", "") for r in server.app.router.routes]
    for required in (
        "/admin",
        "/api/admin/console/overview",
        "/api/admin/console/users",
        "/api/admin/console/points",
        "/api/admin/console/settings",
        "/api/admin/console/audit",
    ):
        assert required in paths, required
    stage("routes verified")

    with db.connect() as con:
        admin = con.execute("SELECT id,name,role,club_verified FROM users WHERE role='admin' ORDER BY id LIMIT 1").fetchone()
        assert admin and admin["name"] == "ケンイチロウ"
        assert int(admin["club_verified"] or 0) == 1
        member = con.execute("SELECT id,name FROM users WHERE role='member' ORDER BY id LIMIT 1").fetchone()
        if not member:
            uid = db.insert_returning_id(con, "INSERT INTO users(name,email,password_hash,role,arena_chips,xp,approved,disabled,ranking_name,created_at,club_verified,admin_note) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", ("テストメンバー", "smoke-member@jj.invalid", db.hash_password("654321"), "member", 0, 0, 1, 0, "テストメンバー", db.utcnow(), 1, ""))
        else:
            uid = int(member["id"])
        con.execute("UPDATE users SET ranking_name='テストメンバー',club_verified=1 WHERE id=?", (uid,))
        con.execute("INSERT INTO point_ledger(id,user_id,amount,kind,reason,effective_at,created_by,created_at,reversal_of) VALUES (?,?,?,?,?,?,?,?,NULL)", ("smoke-credit", uid, 50.0, "credit", "smoke", "2026-09-06T12:00:00", int(admin["id"]), db.utcnow()))
    ranks = _rankings(db, server, season="fall")
    row = next((r for r in ranks if r["name"] == "テストメンバー"), None)
    assert row and row["admin_points"] == 50.0 and row["points"] >= 50.0, row
    stage("ledger ranking integration verified")

    with db.connect() as con:
        con.execute("INSERT INTO point_ledger(id,user_id,amount,kind,reason,effective_at,created_by,created_at,reversal_of) VALUES (?,?,?,?,?,?,?,?,?)", ("smoke-reversal", uid, -50.0, "reversal", "取消: smoke", "2026-09-06T12:00:00", int(admin["id"]), db.utcnow(), "smoke-credit"))
    ranks2 = _rankings(db, server, season="fall")
    row2 = next((r for r in ranks2 if r["name"] == "テストメンバー"), None)
    assert row2 and row2["admin_points"] == 0.0, row2
    stage("ledger reversal verified")

    static = ROOT / "admin_static"
    for f in ("index.html", "admin.css", "admin.js"):
        assert (static / f).is_file() and (static / f).stat().st_size > 100, f
    stage("admin assets verified")

    print("ADMIN_SMOKE_OK", flush=True)


if __name__ == "__main__":
    try:
        main()
    finally:
        shutil.rmtree(WORK, ignore_errors=True)
