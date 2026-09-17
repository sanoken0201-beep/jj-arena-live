"""Canonical JJ Arena production implementation backed by the materialized v1.24.4 core.

The core runtime is loaded from committed source under ``materialized_v1244``
instead of reconstructing historical patches on every startup. Root-level
extension modules remain installed in the same effective order proven by the
legacy/materialized parity gates.

``app.py`` is the stable Render-facing shim. ``app_legacy.py`` retains the
pre-v2 integration shape for parity checks and emergency rollback, but its core
is now an isolated verified copy of the same immutable v1.24.4 snapshot rather
than a replay of the historical patch chain.
"""
from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path

import admin_api_consolidation
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
import point_ledger_precision
import poker_lifecycle_fix
import rake_settlement_fix
import ranking_mapping_guard
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


def _import_materialized_core():
    """Load the canonical bare-import core without polluting global import search.

    The committed v1.24.4 core still uses bare sibling imports (``import db`` and
    ``from poker_engine ...``), so its directory must be first on ``sys.path``
    while ``server`` is imported. Once ``server``, ``db`` and ``poker_engine``
    are resident in ``sys.modules``, root-level integration modules can continue
    resolving those exact module objects without leaving ``materialized_v1244``
    on the process-wide search path.
    """
    original_path = list(sys.path)
    try:
        sys.path.insert(0, str(DEST))
        import server as runtime_server  # noqa: E402
        import db  # noqa: E402
        import poker_engine as runtime_poker_engine  # noqa: E402
    finally:
        sys.path[:] = original_path
    return runtime_server, db, runtime_poker_engine


runtime_server, db, runtime_poker_engine = _import_materialized_core()
app = runtime_server.app

# These root-level integration modules intentionally import the already-loaded
# canonical ``server``/``db`` objects from sys.modules. No persistent path entry
# is needed after the core import above.
import admin_console  # noqa: E402
from admin_delete import install_account_deletion  # noqa: E402


def _require_materialized_module(module, name: str) -> None:
    path = Path(str(getattr(module, "__file__", ""))).resolve()
    if path.parent != DEST:
        raise RuntimeError(f"{name} resolved outside materialized core: {path}")


_require_materialized_module(runtime_server, "server")
_require_materialized_module(db, "db")
_require_materialized_module(runtime_poker_engine, "poker_engine")
if str(DEST) in sys.path:
    raise RuntimeError("materialized core path leaked into process-wide sys.path")

# Snapshot canonical-core route identities before root-level integrations add
# anything. This is retained for diagnostics and parity assertions; route repair
# itself is structural and does not depend on URL-prefix classifications.
_CORE_ROUTE_IDS = frozenset(id(route) for route in app.router.routes)

# Install runtime-only performance improvements after the verified materialized
# modules resolve, without mutating the canonical v1.24.4 source tree or game rules.
runtime_performance.install(db, runtime_server, runtime_poker_engine)

# A live table WebSocket is authoritative presence. This prevents an actively
# playing user from being misclassified as 15-minute idle during the brief
# waiting-state transition immediately after showdown/side-pot settlement.
poker_lifecycle_fix.install(runtime_server)

# Correct uncalled-bet settlement outside the immutable canonical core. The
# refund happens immediately before rake/pot settlement, so only chips actually
# contested by at least two players enter the configured 5% / 3bb rake.
rake_settlement_fix.install(runtime_poker_engine)

# Preserve the already-applied historical migration key. This remains a no-op
# for production databases on which the migration marker already exists.
online_results_cleanup.apply(db)


def _prioritize_extension_routes(fastapi_app, core_route_ids=frozenset()) -> None:
    """Make the canonical SPA catch-all the final route without prefix lists.

    FastAPI evaluates routes in registration order. Any HTTP/API route registered
    after `/{path:path}` is therefore unreachable unless it is moved ahead of the
    SPA fallback. The materialized v1.24.4 source itself contains late analysis
    routes, and root-level integrations append more routes later. Move *all*
    trailing routes, in their existing relative order, immediately before the
    one canonical catch-all. Routes already before the catch-all are untouched.

    ``core_route_ids`` remains an explicit contract argument for diagnostics and
    callers, but routing does not classify by origin or URL prefix.
    """
    routes = list(fastapi_app.router.routes)
    catch_all = [
        route for route in routes
        if str(getattr(route, "path", "") or "") == "/{path:path}"
    ]
    if len(catch_all) != 1:
        raise RuntimeError(f"expected exactly one SPA catch-all, found={len(catch_all)}")

    spa_route = catch_all[0]
    spa_index = routes.index(spa_route)
    trailing = routes[spa_index + 1 :]
    if not trailing:
        return
    fastapi_app.router.routes[:] = routes[:spa_index] + trailing + [spa_route]


admin_console.install_admin_console(app)
point_ledger_precision.ensure_exact_point_ledger(db)
admin_ledger_stabilization.install(app, admin_console)
install_account_deletion(app)
ranking_mapping_guard.install(app, db)
# Keep the historical URL installed as a disabled compatibility endpoint. It no
# longer verifies user PIN candidates; see admin_pin_verification.py.
admin_pin_verification.install(app, admin_console)
security_hardening.install(app, runtime_server, db)
# From this point onward all user/account mutations are canonical under
# /api/admin/console. Legacy /api/admin/members remains read-only compatibility.
admin_api_consolidation.install(app, runtime_server)
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