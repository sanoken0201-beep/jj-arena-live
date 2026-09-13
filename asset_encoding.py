"""Lossless, bounded process-local encoding of public static assets."""
from __future__ import annotations

import gzip
from functools import lru_cache


def accepts_gzip(value: str) -> bool:
    """Only use explicitly accepted gzip; unknown/malformed offers fall back."""
    for offer in value.lower().split(","):
        coding, *parameters = offer.strip().split(";")
        if coding.strip() != "gzip":
            continue
        quality = 1.0
        for parameter in parameters:
            key, separator, raw = parameter.strip().partition("=")
            if key.strip() == "q":
                try:
                    quality = float(raw.strip()) if separator else 0.0
                except ValueError:
                    return False
        return 0.0 < quality <= 1.0
    return False


@lru_cache(maxsize=4)
def encoded_asset(body: str) -> tuple[bytes, bytes]:
    """Encode/compress once per asset, never once per visitor or poker action."""
    plain = body.encode("utf-8")
    return plain, gzip.compress(plain, compresslevel=6, mtime=0)
