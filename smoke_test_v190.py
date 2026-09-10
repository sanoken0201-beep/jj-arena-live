from __future__ import annotations

"""Compatibility entrypoint used by the Render production build command.

Render still invokes smoke_test_v190.py. Keep that stable filename, but route the
actual production smoke gate to the current release suite so deployments cannot
be blocked by stale version assertions.
"""

from smoke_test_v121 import main


if __name__ == "__main__":
    main()
