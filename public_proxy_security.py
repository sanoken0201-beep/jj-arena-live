from __future__ import annotations

from collections.abc import Mapping
from urllib.parse import urlsplit

UNSAFE_BROWSER_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _header(headers: Mapping[str, str], name: str) -> str:
    wanted = name.lower()
    for key, value in headers.items():
        if str(key).lower() == wanted:
            return str(value or "").strip()
    return ""


def _default_port(scheme: str) -> int | None:
    if scheme.lower() in {"https", "wss"}:
        return 443
    if scheme.lower() in {"http", "ws"}:
        return 80
    return None


def _origin_matches_host(value: str, host: str) -> bool:
    """Return True only when an explicit browser origin/referer matches Host."""
    value = str(value or "").strip()
    host = str(host or "").strip()
    if not value or not host:
        return False
    try:
        origin = urlsplit(value)
        if origin.scheme.lower() not in {"http", "https"} or not origin.hostname:
            return False
        host_parts = urlsplit("//" + host)
        if not host_parts.hostname:
            return False
        if origin.hostname.lower().rstrip(".") != host_parts.hostname.lower().rstrip("."):
            return False
        origin_port = origin.port or _default_port(origin.scheme)
        host_port = host_parts.port or _default_port(origin.scheme)
        return origin_port == host_port
    except (TypeError, ValueError):
        return False


def _browser_http_allowed(method: str, headers: Mapping[str, str]) -> bool:
    if str(method or "").upper() not in UNSAFE_BROWSER_METHODS:
        return True
    if _header(headers, "sec-fetch-site").lower() == "cross-site":
        return False
    host = _header(headers, "host")
    origin = _header(headers, "origin")
    if origin:
        return _origin_matches_host(origin, host)
    referer = _header(headers, "referer")
    if referer:
        return _origin_matches_host(referer, host)
    # Native/testing clients do not necessarily send browser origin metadata.
    return True


def _browser_websocket_allowed(headers: Mapping[str, str]) -> bool:
    if _header(headers, "sec-fetch-site").lower() == "cross-site":
        return False
    origin = _header(headers, "origin")
    if not origin:
        return True
    return _origin_matches_host(origin, _header(headers, "host"))


__all__ = [
    "UNSAFE_BROWSER_METHODS",
    "_browser_http_allowed",
    "_browser_websocket_allowed",
    "_origin_matches_host",
]
