"""Process-model guard for JJ Arena's in-process poker schedulers.

Ring and Sit&Go table locks, websocket hubs, and the Sit&Go lifecycle owner are
process-local. Production therefore intentionally runs one ASGI worker. The
Render start command pins that value, and this module fails fast if a deployment
explicitly advertises a conflicting worker count.
"""
from __future__ import annotations

import os


def require_single_worker() -> None:
    for key in ("WEB_CONCURRENCY", "UVICORN_WORKERS"):
        raw = str(os.getenv(key, "") or "").strip()
        if not raw:
            continue
        try:
            workers = int(raw)
        except ValueError as exc:
            raise RuntimeError(f"{key} must be an integer; JJ Arena requires one worker") from exc
        if workers != 1:
            raise RuntimeError(
                f"{key}={workers} is unsafe: JJ Arena requires exactly one ASGI worker"
            )


__all__ = ["require_single_worker"]
