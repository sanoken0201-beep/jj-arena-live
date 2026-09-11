from __future__ import annotations

import re
import tempfile
from pathlib import Path

from runtime_builder import RUNTIME_VERSION, build_runtime


def _rgb(hex_color: str) -> tuple[int, int, int]:
    value = hex_color.lstrip("#")
    return tuple(int(value[i:i+2], 16) for i in (0, 2, 4))


def _rel_lum(rgb: tuple[int, int, int]) -> float:
    def channel(v: int) -> float:
        x = v / 255.0
        return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(fg: str, bg: str) -> float:
    a, b = _rel_lum(_rgb(fg)), _rel_lum(_rgb(bg))
    light, dark = max(a, b), min(a, b)
    return (light + 0.05) / (dark + 0.05)


def main() -> None:
    assert RUNTIME_VERSION == "1.24.2"
    with tempfile.TemporaryDirectory() as td:
        root = build_runtime(Path(td) / "runtime")
        css = (root / "static" / "styles.css").read_text(encoding="utf-8")
        server = (root / "server.py").read_text(encoding="utf-8")
        index = (root / "static" / "index.html").read_text(encoding="utf-8")
        sw = (root / "static" / "sw.js").read_text(encoding="utf-8")

        marker = "v1.24.2 learning-card contrast hardening"
        assert marker in css
        assert css.rfind(marker) > css.rfind("v1.19.2 Japanese-first learning share")

        final = css.split(marker, 1)[1]
        required = (
            ".jj-learning-share .jj-study-card h3",
            ".jj-learning-share .jj-video-card h3",
            ".jj-learning-share .jj-study-meta",
            ".jj-learning-share .jj-study-card footer>span",
            ".jj-learning-share .jj-study-card footer b",
            ".jj-learning-share .jj-study-card:visited",
        )
        for selector in required:
            assert selector in final, selector

        # Regression for the supplied iPhone screenshot: title/meta/date may not
        # inherit the surrounding page's dark text color on the dark green card.
        for color in ("#f7fbf9", "#c9d6d0", "#b8c8c0", "#aebeb6", "#f3d981"):
            assert color in final
        assert "color:inherit" not in final
        assert "opacity:1!important" in final

        # Approximate the darkest visible card surface from the production theme.
        # All normal-size text roles comfortably exceed WCAG AA (4.5:1).
        bg = "#17241f"
        assert _contrast("#f7fbf9", bg) >= 7.0
        assert _contrast("#c9d6d0", bg) >= 4.5
        assert _contrast("#b8c8c0", bg) >= 4.5
        assert _contrast("#aebeb6", bg) >= 4.5
        assert _contrast("#f3d981", bg) >= 4.5

        # Cache bust is required because the reported bug is on mobile Safari.
        assert 'version="1.24.2"' in server or '"version":"1.24.2"' in server
        assert 'request.url.query == "v=54"' in server
        assert "?v=54" in index
        assert "jj-arena-live-v54" in sw

    print("JJ_LEARNING_CONTRAST_SMOKE_OK")


if __name__ == "__main__":
    main()
