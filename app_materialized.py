"""Parity candidate entrypoint for JJ Arena's materialized v1.24.4 core.

This module intentionally mirrors production ``app.py``. The only architectural
change in Phase 1 is that the core runtime is loaded from committed source under
``materialized_v1244`` instead of being reconstructed from the historical patch
chain on every startup.

Do not use this as the Render production entrypoint until the legacy-vs-
materialized parity gates are green and the cutover is reviewed separately.
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

ROOT = Path(__file__).resolve().parent
DEST = (ROOT / "materialized_v1244").resolve()

if not (DEST / "server.py").is_file():
    raise RuntimeError(f"materialized v1.24.4 core is missing: {DEST}")

admin_copy_patch.apply(ROOT / "admin_static")

# Preserve the current PIN-authentication bootstrap semantics exactly.
os.environ["JJ_ADMIN_PASSWORD"] = secrets.token_urlsafe(32)
os.environ.pop("JJ_ADMIN_LOGIN_PASSWORD", None)
os.environ.pop("JJ_ADMIN_LOGIN_EMAIL", None)

# Phase 1 deliberately preserves the legacy bare-import resolution semantics.
# Package-relative import cleanup is a later refactor after behavioral parity.
sys.path.insert(0, str(DEST))
import server as runtime_server  # noqa: E402
from server import app  # noqa: E402
import admin_console  # noqa: E402
import db  # noqa: E402
import poker_engine as runtime_poker_engine  # noqa: E402
from admin_delete import install_account_deletion  # noqa: E402


def _require_materialized_module(module, name: str) -> None:
    path = Path(str(getattr(module, "__file__", ""))).resolve()
    if path.parent != DEST:
        raise RuntimeError(f"{name} resolved outside materialized core: {path}")


_require_materialized_module(runtime_server, "server")
_require_materialized_module(db, "db")
_require_materialized_module(runtime_poker_engine, "poker_engine")

# Preserve the already-applied historical migration key. This remains a no-op
# for production databases on which the migration marker already exists.
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
learning_content.install(app)
daily_quiz.install(app, runtime_server, db)
hand_analytics.install(app, runtime_server, db)
hand_analytics_hardening.install(hand_analytics, runtime_server)
operations_learning.install(app, runtime_server, db, hand_analytics, daily_quiz, learning_content, admin_console)
operations_learning_hardening.apply(operations_learning, db, hand_analytics)
resilience.install(app, runtime_server, db, admin_console)
_prioritize_extension_routes(app)
