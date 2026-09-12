from __future__ import annotations

"""Compatibility entrypoint used by the Render production build command.

Render keeps invoking smoke_test_v190.py. Route that stable filename to the
current release suite, player-facing copy validation, and the runtime
performance regression so a deploy cannot publish a runtime whose final
analysis/review UX, explicit poker labels, or event-driven load-safety layer
failed validation.
"""

from smoke_test_clear_poker_copy import main as clear_copy_main
from smoke_test_runtime_performance import main as performance_main
from smoke_test_v1244 import main as release_main


if __name__ == "__main__":
    clear_copy_main()
    performance_main()
    release_main()
