from __future__ import annotations

"""Compatibility entrypoint used by the Render production build command.

Render keeps invoking smoke_test_v190.py. Route that stable filename to the
current release suite and the runtime performance regression so a deploy cannot
publish a runtime whose final analysis/review UX or event-driven load-safety
layer failed validation. Player-facing copy is validated by the production
asset regression, which exercises the final served app.js and styles.css.
"""

from smoke_test_runtime_performance import main as performance_main
from smoke_test_v1244 import main as release_main


if __name__ == "__main__":
    performance_main()
    release_main()
