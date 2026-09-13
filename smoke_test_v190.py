from __future__ import annotations

"""Compatibility entrypoint used by the Render production build command.

Render keeps invoking smoke_test_v190.py. Compile the immutable-core-derived
browser assets first, then run the release and runtime-performance gates. The
resulting `.jj_build/` directory is part of the build artifact consumed by
`app.py`; production startup itself never runs the UX transform chain.
"""

from build_served_assets import main as build_assets_main
from smoke_test_runtime_performance import main as performance_main
from smoke_test_v1244 import main as release_main


if __name__ == "__main__":
    build_assets_main()
    performance_main()
    release_main()
