from __future__ import annotations

from public_proxy import _browser_http_allowed, _browser_websocket_allowed, _origin_matches_host


def main() -> None:
    host = "jj-arena-club.onrender.com"

    assert _origin_matches_host("https://jj-arena-club.onrender.com", host)
    assert _origin_matches_host("https://jj-arena-club.onrender.com:443", host)
    assert not _origin_matches_host("https://evil.example", host)
    assert not _origin_matches_host("null", host)

    assert _browser_http_allowed("GET", {"host": host, "origin": "https://evil.example"})
    assert _browser_http_allowed("POST", {"host": host, "origin": f"https://{host}"})
    assert not _browser_http_allowed("POST", {"host": host, "origin": "https://evil.example"})
    assert not _browser_http_allowed("DELETE", {"host": host, "referer": "https://evil.example/x"})
    assert not _browser_http_allowed("PATCH", {"host": host, "sec-fetch-site": "cross-site"})
    assert _browser_http_allowed("POST", {"host": host})  # native/non-browser compatibility

    assert _browser_websocket_allowed({"host": host, "origin": f"https://{host}"})
    assert not _browser_websocket_allowed({"host": host, "origin": "https://evil.example"})
    assert not _browser_websocket_allowed({"host": host, "sec-fetch-site": "cross-site"})
    assert _browser_websocket_allowed({"host": host})  # native/non-browser compatibility

    print("JJ_PUBLIC_PROXY_SECURITY_OK")


if __name__ == "__main__":
    main()
