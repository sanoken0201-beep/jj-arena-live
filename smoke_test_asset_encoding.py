"""Verify actual production asset responses without touching a production DB."""
from __future__ import annotations

import gzip
import os
import tempfile


def main():
    with tempfile.TemporaryDirectory(prefix="jj-asset-test-") as directory:
        os.environ["DATABASE_URL"] = ""
        os.environ["JJ_DB_PATH"] = directory + "/test.db"
        from fastapi.testclient import TestClient
        import app
        from asset_encoding import accepts_gzip, encoded_asset

        for offer in ("gzip", "br, gzip, deflate", "GZip; q=0.5"):
            assert accepts_gzip(offer), offer
        for offer in ("", "br", "*", "gzip;q=0", "gzip;q=bad", "gzip;q=2", "gzip;q=nan"):
            assert not accepts_gzip(offer), offer

        encoded_asset.cache_clear()
        with TestClient(app.app) as client:
            for path, source in (("/static/app.js?v=68", app._patched_app_js()),
                                 ("/static/styles.css?v=68", app._patched_styles())):
                expected = source.encode("utf-8")
                plain = client.get(path, headers={"Accept-Encoding": "identity"})
                zipped = client.get(path, headers={"Accept-Encoding": "gzip"})
                assert plain.status_code == zipped.status_code == 200
                assert plain.content == zipped.content == expected
                assert "content-encoding" not in plain.headers
                assert zipped.headers["content-encoding"] == "gzip"
                assert plain.headers["vary"] == zipped.headers["vary"] == "Accept-Encoding"
                assert plain.headers["cache-control"] == zipped.headers["cache-control"]
                assert plain.headers["content-type"] == zipped.headers["content-type"]
                original, compressed, etag = encoded_asset(source)
                assert gzip.decompress(compressed) == original == expected
                assert int(zipped.headers["content-length"]) == len(compressed)
                assert plain.headers["etag"] == zipped.headers["etag"] == etag
                for validator in (etag, etag.removeprefix("W/"), '"old", ' + etag, "*"):
                    for method in (client.get, client.head):
                        cached = method(path, headers={"If-None-Match": validator, "Accept-Encoding": "gzip"})
                        assert cached.status_code == 304 and cached.content == b""
                        assert cached.headers["etag"] == etag
                        assert cached.headers["vary"] == "Accept-Encoding"
                        assert "content-length" not in cached.headers
                changed = client.get(path, headers={"If-None-Match": 'W/"old"'})
                assert changed.status_code == 200 and changed.content == expected
                for offer, length in (("gzip", len(compressed)), ("identity", len(expected)), ("gzip;q=0", len(expected))):
                    head = client.head(path, headers={"Accept-Encoding": offer})
                    assert head.status_code == 200 and head.content == b""
                    assert int(head.headers["content-length"]) == length
                print(f"{path}: {len(expected)} -> {len(compressed)} bytes ({100 * (1-len(compressed)/len(expected)):.1f}% reduction)")
            assert encoded_asset.cache_info().misses == 2
            for path in ("/", "/static/sw.js"):
                response = client.get(path, headers={"Accept-Encoding": "gzip"})
                assert response.status_code == 200
                assert "content-encoding" not in response.headers
            assert client.get("/api/health").status_code == 200
        print("LOSSLESS_ASSET_TRANSFER_OK")


if __name__ == "__main__":
    main()
