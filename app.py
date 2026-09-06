"""Atomic production entrypoint for JJ Arena Live v1.18.5.

The verified v1.4 release bundle remains the immutable base. v1.5 upgrades
authentication, v1.6 upgrades official point entry to chip counts, v1.7
separates Fall 2026/27 rankings from archived Summer totals, v1.8 delivers
the public-launch UI/performance polish, v1.9 adds the weekly Cash/MTT study
spotlight, v1.10 redesigns smartphone operations and removes duplicate
non-admin ケンイチロウ accounts, v1.11 refines mobile navigation state,
v1.12 puts the quick point-entry form directly on Home on every device,
v1.13 adds optional member profiles and member-only profile browsing,
v1.14 rebuilds the online table for continuous play, unanimous first READY,
next-hand sit-out, pot-percentage sizing, and premium bet/card visibility,
v1.14.1 restores explicit 150bb Rebuy plus safer preflop sizing presets,
v1.14.2 clears inter-hand results before each new deal, v1.15 rebuilds the
poker workspace as a contained responsive game stage with a separate utility
column, v1.15.1 completes mobile action clearance plus exact hero hand labels,
v1.16 introduces an explicit table-state model with active player counts,
join-during-hand seat reservation, direct fixed-stack seating, and persisted
state invariant repair, v1.16.1 hardens continuous sessions with revocable
first-deal READY, timeout auto-sitout, cross-table seat serialization, and
immediate authoritative leave refresh, v1.16.2 makes seating a primary
server-selected action visible both in the lobby and on the table itself,
v1.16.3 fixes the table-presence global/function name collision that caused
GET /api/tables/{id} to fail before the seating UI could render, v1.17
rebuilds the phone table as an immersive poker-only surface without competing
site navigation, duplicate seating controls, or blocking result overlays,
v1.18 adds the administrator control center, immutable point adjustment
ledger, account verification controls, policy settings, and audit trail,
v1.18.1 guarantees admin routes are evaluated before the SPA fallback,
v1.18.2 adds irreversible administrator account deletion while preserving
historical ranking, point-ledger, and audit integrity, v1.18.3 standardizes
ambiguous user-facing terminology across poker presence, account state, member
verification, and official point administration, v1.18.4 rebuilds the
phone poker surface around a portrait-first tall-oval table and bottom thumb
zone while leaving landscape and desktop geometry unchanged, and v1.18.5
simplifies mobile poker decisions, makes bet amounts explicit, exposes sizing
presets without scrolling, strengthens touch targets, and adds reduced-motion
support without changing game rules or action semantics.
"""
from __future__ import annotations

import base64
import hashlib
import io
import os
import secrets
import shutil
import sys
import tarfile
from pathlib import Path

import v15_patch
import v16_patch
import v17_patch
import v18_patch
import v19_patch
import v20_patch
import v21_patch
import v22_patch
import v23_patch
import v24_patch
import v25_patch
import v26_patch
import v27_patch
import v28_patch
import v29_patch
import v30_patch
import v31_patch
import v32_patch
import v33_patch
import v34_patch
import v35_patch
import v36_patch
import v37_patch
import admin_copy_patch

ROOT = Path(__file__).resolve().parent
RELEASE_DIR = ROOT / "release_v14"
EXPECTED_SHA256 = "3ccb973f9ab146ce1c0d7da598242b0c1521a8ecc85c091caa10c1f1ebc9ddfd"
DEST = Path("/tmp/jj_arena_v37_runtime")

parts = sorted(RELEASE_DIR.glob("part*.b64"))
if len(parts) != 62:
    raise RuntimeError(f"JJ Arena release bundle incomplete: expected 62 parts, found {len(parts)}")

encoded = "".join(part.read_text(encoding="utf-8").strip() for part in parts)
raw = base64.b64decode(encoded, validate=True)
actual_sha256 = hashlib.sha256(raw).hexdigest()
if actual_sha256 != EXPECTED_SHA256:
    raise RuntimeError(f"JJ Arena release bundle checksum mismatch: {actual_sha256}")

shutil.rmtree(DEST, ignore_errors=True)
DEST.mkdir(parents=True, exist_ok=True)
dest_root = DEST.resolve()
with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
    for member in archive.getmembers():
        target = (DEST / member.name).resolve()
        if target != dest_root and dest_root not in target.parents:
            raise RuntimeError("Unsafe path detected in JJ Arena release bundle")
    archive.extractall(DEST)

v15_patch.apply(DEST)
v16_patch.apply(DEST)
v17_patch.apply(DEST)
v18_patch.apply(DEST, ROOT / "v18_assets")
v19_patch.apply(DEST)
v20_patch.apply(DEST)
v21_patch.apply(DEST)
v22_patch.apply(DEST)
v23_patch.apply(DEST)
v24_patch.apply(DEST)
v25_patch.apply(DEST)
v26_patch.apply(DEST)
v27_patch.apply(DEST)
v28_patch.apply(DEST)
v29_patch.apply(DEST)
v30_patch.apply(DEST)
v31_patch.apply(DEST)
v32_patch.apply(DEST)
v33_patch.apply(DEST)
v34_patch.apply(DEST)
v35_patch.apply(DEST)
v36_patch.apply(DEST)
v37_patch.apply(DEST)
admin_copy_patch.apply(ROOT / "admin_static")

# The legacy Render shell command still exports/logs JJ_ADMIN_PASSWORD. v1.18+
# does not use that credential, but overwrite it anyway so the logged value can
# never authenticate to the application. Old email/password recovery is disabled.
os.environ["JJ_ADMIN_PASSWORD"] = secrets.token_urlsafe(32)
os.environ.pop("JJ_ADMIN_LOGIN_PASSWORD", None)
os.environ.pop("JJ_ADMIN_LOGIN_EMAIL", None)

sys.path.insert(0, str(DEST))
from server import app  # noqa: E402
from admin_console import install_admin_console  # noqa: E402
from admin_delete import install_account_deletion  # noqa: E402


def _prioritize_admin_routes(fastapi_app) -> None:
    """Move admin routes ahead of the legacy SPA catch-all."""
    routes = list(fastapi_app.router.routes)

    def is_admin_route(route) -> bool:
        path = str(getattr(route, "path", "") or "")
        return (
            path in {"/admin", "/admin/"}
            or path.startswith("/admin-static")
            or path.startswith("/api/admin/console")
        )

    admin_routes = [route for route in routes if is_admin_route(route)]
    other_routes = [route for route in routes if not is_admin_route(route)]
    fastapi_app.router.routes[:] = admin_routes + other_routes


install_admin_console(app)
install_account_deletion(app)
_prioritize_admin_routes(app)
