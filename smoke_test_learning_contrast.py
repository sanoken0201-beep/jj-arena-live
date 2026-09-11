from __future__ import annotations

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


def _version_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))


def main() -> None:
    # Contrast hardening was introduced in v1.24.2 and must survive later
    # releases; this is intentionally not an exact release-number gate.
    assert _version_tuple(RUNTIME_VERSION) >= (1, 24, 2)
    with tempfile.TemporaryDirectory() as td:
        root = build_runtime(Path(td) / "runtime")
        css = (root / "static" / "styles.css").read_text(encoding="utf-8")
        server = (root / "server.py").read_text(encoding="utf-8")
        index = (root / "static" / "index.html").read_text(encoding="utf-8")
        sw = (root / "static" / "sw.js").read_text(encoding="utf-8")

        marker = "v1.24.2 learning-card contrast hardening"
        assert marker in css
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
        for color in ("#f7fbf9", "#c9d6d0", "#b8c8c0", "#aebeb6", "#f3d981"):
            assert color in final
        bg = "#17241f"
        assert _contrast("#f7fbf9", bg) >= 7.0
        assert _contrast("#c9d6d0", bg) >= 4.5
        assert _contrast("#b8c8c0", bg) >= 4.5
        assert _contrast("#aebeb6", bg) >= 4.5
        assert _contrast("#f3d981", bg) >= 4.5

        assert f'version="{RUNTIME_VERSION}"' in server or f'"version":"{RUNTIME_VERSION}"' in server
        assert 'request.url.query == "v=' in server
        assert "?v=" in index
        assert "jj-arena-live-v" in sw
        assert "v1.24.3 focused non-poker product UX" in css

    print("JJ_LEARNING_CONTRAST_SMOKE_OK")


if __name__ == "__main__":
    main()
