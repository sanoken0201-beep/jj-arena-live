from __future__ import annotations

import math

import served_assets


def ceil_bb1(value: float) -> float:
    return math.ceil((float(value) - 1e-9) * 10.0) / 10.0


def js_round_positive(value: float) -> int:
    return math.floor(float(value) + 0.5)


def snap_sng_bb(value: float, *, big: int, unit: int, min_chips: int, max_chips: int) -> float:
    chips = js_round_positive((float(value) * big) / unit) * unit
    if min_chips:
        chips = max(min_chips, chips)
    if max_chips:
        chips = min(max_chips, chips)
    return chips / big


def route_ring_raise(entered: float, *, min_bb: float, max_bb: float, big: int, can_all_in: bool):
    value = ceil_bb1(entered)
    display_min = ceil_bb1(min_bb)
    display_max = ceil_bb1(max_bb)
    if value < display_min - 0.001 or value > display_max + 0.001:
        return ("invalid", None)
    if can_all_in and max_bb > 0 and abs(value - display_max) < 0.011:
        return ("allin", None)
    return ("raise", round(value * big))


def main() -> None:
    # Product precision contract: one visible decimal, always rounded upward.
    assert ceil_bb1(6.23) == 6.3
    assert ceil_bb1(6.21) == 6.3
    assert ceil_bb1(6.20) == 6.2
    assert ceil_bb1(3.001) == 3.1
    assert ceil_bb1(3.0) == 3.0

    # The bug case: rounded display maximum must become an exact all-in action,
    # never an oversized numeric raise.
    assert route_ring_raise(6.3, min_bb=2.0, max_bb=6.23, big=100, can_all_in=True) == ("allin", None)
    assert route_ring_raise(6.23, min_bb=2.0, max_bb=6.23, big=100, can_all_in=True) == ("allin", None)

    # Ordinary values are also canonicalized upward to one decimal.
    assert route_ring_raise(3.21, min_bb=2.0, max_bb=9.0, big=100, can_all_in=True) == ("raise", 330)
    assert route_ring_raise(2.01, min_bb=2.01, max_bb=9.0, big=100, can_all_in=True) == ("raise", 210)

    # Sit&Go continues to send denomination-safe chip totals internally even
    # though the player sees only one decimal BB.
    exact = snap_sng_bb(2.1, big=1400, unit=100, min_chips=2800, max_chips=7000)
    chips = round(exact * 1400)
    assert chips == 2900
    assert chips % 100 == 0
    assert ceil_bb1(exact) == 2.1

    js = served_assets.build_app_js()
    assert "function jjV124CeilRaiseBb(value)" in js
    assert "Math.ceil((n-1e-9)*10)/10" in js
    assert "jjV124FmtNumber(displayMin,1)" in js
    assert "draft.text=jjV124FmtNumber(clamped,1)" in js
    assert "body.action='allin';" in js
    assert "const roundedMaxAllin=legal.can_all_in" in js
    assert "jjSngSnapRaiseBb(value)" in js
    assert "input.value=String(typeof jjV124CeilRaiseBb==='function'?jjV124CeilRaiseBb(exact):exact)" in js
    assert "jjV124FmtNumber(min,2)" not in js
    assert "jjV124FmtNumber(clamped,2)" not in js

    print("JJ_BET_PRECISION_OK", flush=True)


if __name__ == "__main__":
    main()
