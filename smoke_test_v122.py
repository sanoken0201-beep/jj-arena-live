from __future__ import annotations

import tempfile
from pathlib import Path

from daily_quiz import BANK_VERSION, build_daily_questions
from quiz_bank import POOLS
from quiz_readability import PLAIN_CATEGORY_LABELS, audit_questions, make_readable
from runtime_builder import RUNTIME_VERSION, build_runtime


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
    assert all(q["reward"] == 10 for q in [dict(q, reward=10) for q in today])
    assert all("chipEV" not in q["prompt"] for q in today)
    assert all("OOP" not in q["prompt"] or q["category"] == "vocabulary" for q in today)
    assert all("IP" not in q["prompt"] or q["category"] == "vocabulary" for q in today)

    # Known formerly jargon-heavy questions must now be self-contained.
    equity_raw = next(q for q in POOLS["equity"] if q["key"].startswith("decision-"))
    equity = make_readable(equity_raw)
    assert "chipEV" not in equity["prompt"] and "ICM" not in equity["prompt"]
    assert "チップの増減だけで見た長期的な平均損益" in equity["prompt"]
    mdf = make_readable(next(q for q in POOLS["mdf"] if "MDF" in q["prompt"]))
    assert "最低継続率（MDF）" in mdf["prompt"]
    term = make_readable(next(q for q in POOLS["vocabulary"] if q["key"] == "term-spr"))
    assert "実際に賭け合える残りチップ" in term["prompt"]
    assert any(c["label"] == "エフェクティブスタック ÷ ポット" for c in term["choices"])

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
        assert "jj-v122-street" in css
        assert "jj-v122-action hero" in appjs
        assert "jj-v122-review-grid" in css
        assert "@media(max-width:640px)" in css
        assert "?v=50" in index
        assert "jj-arena-live-v50" in sw

        # Card privacy implementation remains in the built poker engine.
        engine = (root / "poker_engine.py").read_text(encoding="utf-8")
        assert "completed-hand card privacy" in engine
        assert "uid in showdown_ids" in engine
        assert '["??", "??"]' in engine

    print("v1.22 smoke: ok")


if __name__ == "__main__":
    main()
