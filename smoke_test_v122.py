from __future__ import annotations

import tempfile
from pathlib import Path

from daily_quiz import BANK_VERSION, build_daily_questions
from quiz_bank import POOLS
from quiz_readability import PLAIN_CATEGORY_LABELS, audit_questions, make_readable
from runtime_builder import RUNTIME_VERSION, build_runtime


def _sample(category: str, prompt: str) -> dict:
    return {
        "key": "test",
        "category": category,
        "category_label": "old",
        "prompt": prompt,
        "choices": [
            {"value": "a", "label": "A"},
            {"value": "b", "label": "B"},
            {"value": "c", "label": "C"},
            {"value": "d", "label": "D"},
        ],
        "correct": "a",
        "explanation": "テスト用の十分な長さの解説です。判断の理由を確認します。",
    }


def main() -> None:
    assert RUNTIME_VERSION == "1.22.0"
    assert BANK_VERSION == "2026-09-11-v2-readable"
    assert len(POOLS) == 10
    assert sum(len(pool) for pool in POOLS.values()) == 160

    errors = audit_questions(POOLS)
    assert not errors, "quiz readability audit failed:\n" + "\n".join(errors[:30])

    today = build_daily_questions("2026-09-11")
    assert len(today) == 10
    assert len({q["category"] for q in today}) == 10
    assert all(q["category_label"] == PLAIN_CATEGORY_LABELS[q["category"]] for q in today)
    assert all(len(q["choices"]) == 4 for q in today)

    # Regression for ASCII poker abbreviations adjacent to Japanese characters.
    mdf = make_readable(_sample("mdf", "ポット100、ベット50。MDFは何%ですか？"))
    assert "最低継続率（MDF）" in mdf["prompt"]
    assert "MDFは" not in mdf["prompt"]
    spr = make_readable(_sample("spr", "SPRが低いOOP側の判断は？"))
    assert "現在のポット（SPR）" in spr["prompt"]
    assert "先に行動する側（OOP）" in spr["prompt"]
    equity = make_readable(_sample("equity", "レーキ・ICM・タイを無視したchipEVで判断します。"))
    assert "chipEV" not in equity["prompt"] and "ICM" not in equity["prompt"]
    assert "チップの増減だけで見た長期的な平均損益" in equity["prompt"]

    with tempfile.TemporaryDirectory() as td:
        root = build_runtime(Path(td) / "runtime")
        server = (root / "server.py").read_text(encoding="utf-8")
        appjs = (root / "static" / "app.js").read_text(encoding="utf-8")
        css = (root / "static" / "styles.css").read_text(encoding="utf-8")
        index = (root / "static" / "index.html").read_text(encoding="utf-8")
        sw = (root / "static" / "sw.js").read_text(encoding="utf-8")

        assert 'version="1.22.0"' in server or '"version":"1.22.0"' in server
        assert "v1.22.0 readable quiz and visual hand review" in appjs
        assert "jjV122QuizTerms" in appjs
        assert "jjV122ActionTimeline" in appjs
        assert "ACTION FLOW" in appjs
        assert "YOUR HAND" in appjs
        assert "YOUR REVIEW" in appjs
        assert "Pot ${safe(pot)}" in appjs
        assert "mine?'hero':''" in appjs
        assert ".jj-v122-action.hero" in css
        assert "jj-v122-street" in css
        assert "jj-v122-review-grid" in css
        assert "@media(max-width:640px)" in css
        assert "?v=50" in index
        assert "jj-arena-live-v50" in sw

    print("v1.22 smoke: ok")


if __name__ == "__main__":
    main()
