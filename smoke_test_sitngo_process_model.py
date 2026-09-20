"""Regression for the single-process production contract."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import sitngo_process_guard

ROOT = Path(__file__).resolve().parent


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    render = (ROOT / "render.yaml").read_text(encoding="utf-8")
    require("--workers 1" in render, "Render start command must explicitly pin one uvicorn worker")
    require("key: WEB_CONCURRENCY" in render and 'value: "1"' in render, "Render WEB_CONCURRENCY=1 is missing")

    with patch.dict(os.environ, {"WEB_CONCURRENCY": "1"}, clear=False):
        sitngo_process_guard.require_single_worker()

    with patch.dict(os.environ, {"WEB_CONCURRENCY": "2"}, clear=False):
        try:
            sitngo_process_guard.require_single_worker()
        except RuntimeError as exc:
            require("exactly one ASGI worker" in str(exc), "worker guard error lost its safety explanation")
        else:
            raise AssertionError("multi-worker production configuration was accepted")

    with patch.dict(os.environ, {"WEB_CONCURRENCY": "many"}, clear=False):
        try:
            sitngo_process_guard.require_single_worker()
        except RuntimeError:
            pass
        else:
            raise AssertionError("non-numeric worker configuration was accepted")

    print("JJ_SITNGO_PROCESS_MODEL_OK")


if __name__ == "__main__":
    main()
