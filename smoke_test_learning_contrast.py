from __future__ import annotations

import importlib
import tempfile
from pathlib import Path

from runtime_builder import RUNTIME_VERSION, build_runtime


ROOT = Path(__file__).resolve().parent


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


def _assert_materialized_production_hotfix() -> None:
    # Importing the production entrypoint applies the idempotent compatibility
    # layer before StaticFiles is mounted. This is the exact path Render runs.
    importlib.import_module("app")
    static = ROOT / "materialized_v1244" / "static"
    css = (static / "styles.css").read_text(encoding="utf-8")
    index = (static / "index.html").read_text(encoding="utf-8")
    sw = (static / "sw.js").read_text(encoding="utf-8")

    marker = "v2 today's-jj contrast hardening 2026-09-12"
    assert css.count(marker) == 1, "production hotfix must be idempotent"
    final = css.split(marker, 1)[1]

    # Selectors deliberately do not depend on .jj-learning-share. The cards can
    # move between home layouts without inheriting dark page text again.
    for selector in (
        ".jj-study-card h3",
        ".jj-study-card p",
        ".jj-study-meta",
        ".jj-study-source",
        ".jj-study-card footer",
        ".jj-study-card footer b",
        ".jj-study-card:visited",
    ):
        assert selector in final, selector
    assert ".jj-learning-share .jj-study-card h3" not in final
    assert "-webkit-text-fill-color:#ffffff!important" in final
    assert "-webkit-text-fill-color:#ffe08a!important" in final

    # The screenshot failure is title/date/category visibility on a dark green
    # card. Keep all critical roles comfortably above WCAG AA contrast.
    bg = "#17241f"
    for color in ("#ffffff", "#d7e2dc", "#c4d0ca", "#a8ebcb", "#ffe08a"):
        assert _contrast(color, bg) >= 4.5, (color, _contrast(color, bg))

    # A new URL and SW cache namespace force iOS Safari/LINE in-app browsing to
    # fetch the corrected CSS instead of reusing the pre-hotfix asset forever.
    assert '/static/styles.css?v=57' in index
    assert "const CACHE='jj-arena-live-v57';" in sw
    assert "'/static/styles.css?v=57'" in sw
    assert "'/static/app.js?v=56'" in sw


def main() -> None:
    # Preserve the historical reconstructed-runtime gate so the rollback path
    # remains readable too.
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

    _assert_materialized_production_hotfix()
    print("JJ_LEARNING_CONTRAST_SMOKE_OK")


if __name__ == "__main__":
    main()
