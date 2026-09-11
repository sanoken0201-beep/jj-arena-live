from __future__ import annotations

"""Compatibility entrypoint used by the Render production build command.

Render keeps invoking smoke_test_v190.py. Route that stable filename to the
current release suite so production deploys validate the exact v1.24 runtime.
"""

from smoke_test_v124 import main


if __name__ == "__main__":
    main()
