"""Production entrypoint for JJ Arena Live v1.19.4.

The application runtime is reconstructed deterministically by runtime_builder.py
from the verified v1.4 release bundle plus the ordered patch chain. Keep this
entrypoint small: runtime construction belongs in one place so production and
smoke tests cannot drift apart.
"""
from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path

import admin_copy_patch
import admin_ledger_stabilization
import admin_pin_verification
import learning_content
import online_results_cleanup
from runtime_builder import build_runtime

ROOT = Path(__file__).resolve().parent
DEST = build_runtime()
admin_copy_patch.apply(ROOT / "admin_static")

# Legacy email/password bootstrap variables are not part of the current PIN
# authentication model. Neutralize them before importing the reconstructed app.
os.environ["JJ_ADMIN_PASSWORD"] = secrets.token_urlsafe(32)
os.environ.pop("JJ_ADMIN_LOGIN_PASSWORD", None)
os.environ.pop("JJ_ADMIN_LOGIN_EMAIL", None)

sys.path.insert(0, str(DEST))
from server import app  # noqa: E402
import admin_console  # noqa: E402
import db  # noqa: E402
from admin_delete import install_account_deletion  # noqa: E402

# One-time data migration requested for the online-ranking cleanup. The marker
# makes this a no-op on all subsequent production restarts.
online_results_cleanup.apply(db)


def _prioritize_extension_routes(fastapi_app) -> None:
    """Move extension/API routes ahead of the reconstructed SPA catch-all."""
    routes = list(fastapi_app.router.routes)

    def is_extension_route(route) -> bool:
        path = str(getattr(route, "path", "") or "")
        return (
            path in {"/admin", "/admin/", "/api/learning-content"}
            or path.startswith("/admin-static")
            or path.startswith("/api/admin/console")
        )

    extension_routes = [route for route in routes if is_extension_route(route)]
    other_routes = [route for route in routes if not is_extension_route(route)]
    fastapi_app.router.routes[:] = extension_routes + other_routes


admin_console.install_admin_console(app)
admin_ledger_stabilization.install(app, admin_console)
install_account_deletion(app)
admin_pin_verification.install(app, admin_console)
learning_content.install(app)
_prioritize_extension_routes(app)
