from __future__ import annotations

"""Stable compatibility entrypoint for the Render production build command.

Render continues invoking ``smoke_test_v190.py``. The actual release contract
now lives in ``production_release_gate.py`` and is shared with GitHub CI. That
gate prebuilds the final browser assets and runs only isolated SQLite checks so
the Render build environment's production ``DATABASE_URL`` is never used by
release validation.
"""

from production_release_gate import main


if __name__ == "__main__":
    main()
