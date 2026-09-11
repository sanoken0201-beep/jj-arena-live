from __future__ import annotations

"""Compatibility entrypoint used by the Render production build command.

Render keeps invoking smoke_test_v190.py. Route that stable filename to the
current release suite so a deploy cannot publish a runtime whose final analysis
and review UX layer failed reconstruction checks.
"""

from smoke_test_v1244 import main


if __name__ == "__main__":
    main()
