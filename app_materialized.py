"""Canonical JJ Arena production implementation backed by the materialized v1.24.4 core.

The core runtime is loaded from committed source under ``materialized_v1244``
instead of being reconstructed from the historical patch chain on every
startup. Root-level extension modules remain installed in the same effective
order proven by the Phase 1 legacy/materialized parity gates.

``app.py`` is the stable Render-facing shim. ``app_legacy.py`` retains the
former reconstructed startup path for parity checks and emergency rollback.
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
import hand_history_visibility
import learning_content
import daily_quiz
import online_results_cleanup
import operations_learning
import operations_learning_hardening
import resilience
import runtime_performance
import security_hardening
import ux_telemetry

ROOT = Path(__file__).resolve().parent
DEST = (ROOT / "materialized_v1244").resolve()

if not (DEST / "server.py").is_file():
    raise RuntimeError(f"materialized v1.24.4 core is missing: {DEST}")

admin_copy_patch.apply(ROOT / "admin_static")

# Preserve the current PIN-authentication bootstrap semantics exactly.
os.environ["JJ_ADMIN_PASSWORD"] = secrets.token_urlsafe(32)
os.environ.pop("JJ_ADMIN_LOGIN_PASSWORD", None)
os.environ.pop("JJ_ADMIN_LOGIN_EMAIL", None)

# Preserve the proven bare-import resolution semantics during the cutover.
# Package-relative import cleanup is a later refactor after production burn-in.
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

# Snapshot canonical-core routes before root-level extensions add anything. The
# object identities are stable for the lifetime of this FastAPI instance and
# let us preserve the proven "extensions before core" routing contract without
# maintaining a fragile list of URL prefixes.
_CORE_ROUTE_IDS = frozenset(id(route) for route in app.router.routes)

# Install runtime-only performance improvements after the verified materialized
# modules resolve, without mutating the canonical v1.24.4 source tree or game rules.
runtime_performance.install(db, runtime_server, runtime_poker_engine)

# Preserve the already-applied historical migration key. This remains a no-op
# for production databases on which the migration marker already exists.
online_results_cleanup.apply(db)


def _prioritize_extension_routes(fastapi_app, core_route_ids=frozenset()) -> None:
    """Keep every root-level extension route ahead of canonical core routes.

    Earlier releases classified extensions by URL prefixes. That was unsafe:
    adding a new extension endpoint could be silently shadowed by the core SPA
    catch-all until its prefix was manually added to the list. Route identity
    gives the same effective ordering while automatically covering every future
    root-level extension route.
    """
    routes = list(fastapi_app.router.routes)
    core_ids = frozenset(core_route_ids)
    core_routes = [route for route in routes if id(route) in core_ids]
    extension_routes = [route for route in routes if id(route) not in core_ids]
    if len(core_routes) != len(core_ids):
        raise RuntimeError(
            "canonical route set changed while installing extensions: "
            f"expected={len(core_ids)} found={len(core_routes)}"
        )
    fastapi_app.router.routes[:] = extension_routes + core_routes


admin_console.install_admin_console(app)
admin_ledger_stabilization.install(app, admin_console)
install_account_deletion(app)
# Keep the historical URL installed as a disabled compatibility endpoint. It no
# longer verifies user PIN candidates; see admin_pin_verification.py.
admin_pin_verification.install(app, admin_console)
security_hardening.install(app, runtime_server, db)
learning_content.install(app)
daily_quiz.install(app, runtime_server, db)
hand_analytics.install(app, runtime_server, db)
hand_analytics_hardening.install(hand_analytics, runtime_server)
hand_history_visibility.install(hand_analytics)
operations_learning.install(app, runtime_server, db, hand_analytics, daily_quiz, learning_content, admin_console)
operations_learning_hardening.apply(operations_learning, db, hand_analytics)
resilience.install(app, runtime_server, db, admin_console)
ux_telemetry.install(app, runtime_server, db)
_prioritize_extension_routes(app, _CORE_ROUTE_IDS)
