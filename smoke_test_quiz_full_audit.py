"""Independent, release-gated integrity audit for every authored daily quiz.

This audit is for the 300 static bank items, *not* administrator-generated
questions stored in the production database. No network or database writes.
"""
from __future__ import annotations

import math
import re
from collections import Counter

import quiz_bank
from quiz_advanced_bank import SOURCES
from quiz_expansion_300 import ROWS, validate as validate_300_source
from quiz_readability import audit_questions, make_readable

EXPECTED_DISTRIBUTION = {
    "pot_odds": 30, "equity": 30, "mdf": 30, "spr": 30,
    "combo": 30, "vocabulary": 30, "icm": 30,
    "bet_sizing": 30, "range": 30, "hand_reasoning": 30,
}
NUMERIC_KEY = re.compile(r"(pot|bluff|mdf|spr|decision)-(\d+)-(\d+)\Z")


def correct_label(q: dict) -> str:
    matches = [c["label"] for c in q["choices"] if c["value"] == q["correct"]]
    assert len(matches) == 1, (q["key"], matches)
    return matches[0]


def _legacy_numeric_answer(q: dict) -> bool:
    """Recalculate all 31 generated legacy arithmetic/decision questions."""
    match = NUMERIC_KEY.fullmatch(q["key"])
    if not match:
        return False
    kind, x, y = match.group(1), int(match.group(2)), int(match.group(3))
    answer = correct_label(q)
    if kind == "pot":
        expected = round(100 * y / (x + 2*y))
        assert answer == f"{expected}%", (q["key"], answer, expected)
    elif kind == "bluff":
        expected = round(100 * y / (x+y))
        assert answer == f"{expected}%", (q["key"], answer, expected)
    elif kind == "mdf":
        expected = round(100 * x / (x+y))
        assert answer == f"{expected}%", (q["key"], answer, expected)
    elif kind == "spr":
        expected = x / y  # key order is stack-pot, not pot-stack
        assert math.isclose(float(answer), expected), (q["key"], answer, expected)
    else:
        expected = "コール" if y > x else "フォールド" if y < x else "損益分岐で同じEV"
        assert answer == expected, (q["key"], answer, expected)
    return True


def audit() -> dict[str, int]:
    validate_300_source()
    pools = quiz_bank.POOLS
    assert {category: len(pool) for category, pool in pools.items()} == EXPECTED_DISTRIBUTION
    original = [question for questions in pools.values() for question in questions]
    assert len(original) == 300
    assert len({q["key"] for q in original}) == 300
    assert len({q["prompt"] for q in original}) == 300
    assert not audit_questions(pools), audit_questions(pools)
    sourced_urls = {url for _, url in SOURCES.values()}
    assert all(url.startswith("https://blog.gtowizard.com/") for url in sourced_urls)

    originals = {"legacy": 0, "reviewed_40": 0, "advanced_30": 0, "curated_70": 0}
    math_checked = 0
    for original_q in original:
        key = original_q["key"]
        q = make_readable(original_q)
        assert isinstance(q["prompt"], str) and len(q["prompt"].strip()) > 8, key
        assert len(q["prompt"]) <= 250, key
        assert isinstance(q["explanation"], str) and len(q["explanation"].strip()) >= 15, key
        assert len(q["choices"]) == 4, key
        assert len(set(c["value"] for c in q["choices"])) == 4, key
        assert len(set(c["label"] for c in q["choices"])) == 4, key
        assert all(c["label"].strip() for c in q["choices"]), key
        assert correct_label(original_q).strip(), key
        assert "です." not in q["prompt"], key
        assert "ベット持ちうる手札の候補" not in q["prompt"], key
        assert q["category_label"], key
        if _legacy_numeric_answer(original_q):
            math_checked += 1
        if "-curated300-" in key:
            originals["curated_70"] += 1
        elif "-advanced-" in key:
            originals["advanced_30"] += 1
        elif key in REVIEWED_40_KEYS:
            originals["reviewed_40"] += 1
        else:
            originals["legacy"] += 1
        if "-advanced-" in key or "-curated300-" in key:
            assert original_q["source_url"] in sourced_urls, key
            assert original_q["source_title"], key
        else:
            assert "source_url" not in original_q, key

    assert originals == {"legacy": 160, "reviewed_40": 40, "advanced_30": 30, "curated_70": 70}, originals
    assert math_checked == 31, math_checked
    new_difficulties = Counter(q["difficulty"] for q in original if "-curated300-" in q["key"])
    assert new_difficulties == Counter({"standard": 30, "intermediate": 40}), new_difficulties
    # Human-reviewed mathematical and semantic regressions. The expected results
    # are independently derived from the quantitative assumptions in each stem.
    expected_answers = {
        "pot_odds-curated300-implied-guarantee": "＋10",
        "pot_odds-curated300-rake-adjusted": "21%",
        "pot_odds-curated300-third-player-call": "20%",
        "pot_odds-curated300-raise-to-180": "26%",
        "equity-curated300-win-tie-55": "55%",
        "equity-curated300-flop-eight-clean": "31%",
        "equity-curated300-eqr-inverse": "120%",
        "combo-curated300-blocked-ako-five": "5コンボ",
        "icm-curated300-icm-three-player-prize": "64",
        "range-check-posterior": "40%",
        "spr-curated300-geometry-one": "37%",
        "spr-curated300-geometry-three": "82%",
        "mdf-curated300-bluffcatcher-12": "フォールドが有利です",
        "bet_sizing-advanced-triple-barrel-fold": "72%",
        "bet_sizing-curated300-size-value-ratio-half": "3コンボ",
        "bet_sizing-curated300-size-value-ratio-over": "4コンボ",
        "hand_reasoning-river-indifference": "フォールドと同じ0です",
        "vocabulary-curated300-vocab-backdoor-draw": "バックドア・フラッシュドロー",
        "vocabulary-curated300-vocab-equity-denial": "エクイティ・デナイアル",
        "vocabulary-curated300-vocab-showdown-value": "ショーダウンバリュー",
        "vocabulary-curated300-vocab-merged-bet": "マージドベットレンジ",
        "vocabulary-curated300-vocab-monotone-board": "モノトーンボード",
    }
    by_key = {q["key"]: q for q in original}
    for key, expected in expected_answers.items():
        assert correct_label(by_key[key]) == expected, (key, correct_label(by_key[key]))
    # Specific exact-duplicate teaching goals found in the 300-item review were
    # replaced, while parameterized practice exercises deliberately remain.
    for retired_key in (
        "equity-curated300-win-tie-40",
        "combo-curated300-pair-six",
        "icm-curated300-icm-chipev-diverge",
        "range-fold-blocker",
        "vocabulary-curated300-vocab-range-adv",
        "vocabulary-curated300-vocab-nut-adv",
        "vocabulary-curated300-vocab-blocker",
        "vocabulary-curated300-vocab-unblocker",
        "vocabulary-curated300-vocab-geometric",
    ):
        assert retired_key not in by_key, retired_key

    # Independent recomputation for the two especially subtle added items.
    assert math.isclose(0.4 + 0.3/2, 0.55)
    assert math.comb(2, 1) * math.comb(3, 1) - 1 == 5
    second_probability = (30/100)*(50/(50+20)) + (20/100)*(50/(50+30))
    assert round(100*(50/100) + 40*second_probability) == 64
    assert (4*0.5)/(4*0.5+12*0.25) == .4

    # The public user flow uses the same make_readable output, preserving the
    # keyed answer value while avoiding leaked sources before the answer API.
    print("JJ_QUIZ_FULL_AUDIT_OK", {"total": len(original), "categories": len(pools),
                                      "legacy_numeric_checked": math_checked,
                                      "source_backed": originals["advanced_30"]+originals["curated_70"],
                                      **originals})
    return originals


# Captures exact keys of the independently authored 2026-10-11 addition.
REVIEWED_40_KEYS = {
    f"{category}-{line.split('|')[0]}"
    for category, raw in quiz_bank._REVIEWED_202610.items()
    for line in raw.strip().splitlines()
}


if __name__ == "__main__":
    audit()
