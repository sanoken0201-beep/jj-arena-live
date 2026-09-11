"""Production entrypoint for JJ Arena Live after the v2 core materialization cutover.

Render continues to start ``app:app``. This shim delegates to the committed,
verified materialized v1.24.4 implementation so production no longer rebuilds
the historical patch chain on every process start.

The former reconstructed startup path remains in ``app_legacy.py`` as the
parity oracle and rollback reference.
"""
from __future__ import annotations

from app_materialized import app, db, runtime_poker_engine, runtime_server

__all__ = ["app", "db", "runtime_poker_engine", "runtime_server"]
