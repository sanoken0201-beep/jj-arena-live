"""Render compatibility entrypoint.

The Render service was initially created with `uvicorn app:app`. The actual
application now lives in server.py; keep this shim so the public URL can be
upgraded without recreating the Render service.
"""
from server import app
