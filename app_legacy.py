"""Legacy reconstructed production entrypoint retained for rollback and parity.

This is the pre-v2-cutover production entrypoint. It reconstructs the verified
v1.24.4 runtime through runtime_builder.py and the historical patch chain.
Security extensions are intentionally shared with the materialized path so an
emergency rollback cannot weaken the active authentication boundary.
"""
from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path

import admin_copy_patch
import admin_ledger_stabilization
import admin_pin_verification
import hand_analytics
import hand_analytics_hardening
import learning_content
import daily_quiz
import online_results_cleanup
import operations_learning
import operations_learning_hardening
import resilience
import security_hardening
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
import server as runtime_server  # noqa: E402
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
            or path.startswith("/api/analysis")
            or path.startswith("/api/quiz/")
            or path.startswith("/api/home/")
        )

    extension_routes = [route for route in routes if is_extension_route(route)]
    other_routes = [route for route in routes if not is_extension_route(route)]
    fastapi_app.router.routes[:] = extension_routes + other_routes


admin_console.install_admin_console(app)
admin_ledger_stabilization.install(app, admin_console)
install_account_deletion(app)
admin_pin_verification.install(app, admin_console)
security_hardening.install(app, runtime_server, db)
learning_content.install(app)
daily_quiz.install(app, runtime_server, db)
hand_analytics.install(app, runtime_server, db)
hand_analytics_hardening.install(hand_analytics, runtime_server)
operations_learning.install(app, runtime_server, db, hand_analytics, daily_quiz, learning_content, admin_console)
operations_learning_hardening.apply(operations_learning, db, hand_analytics)
resilience.install(app, runtime_server, db, admin_console)
_prioritize_extension_routes(app)