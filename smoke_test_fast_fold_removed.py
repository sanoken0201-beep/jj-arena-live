from __future__ import annotations

from poker_client_cleanup import remove_fast_fold
from served_assets import build_app_js


def main() -> None:
    built = build_app_js()
    cleaned = remove_fast_fold(built)

    # Manual fold remains part of the authoritative action bar.
    assert 'data-action="fold"' in cleaned
    assert '<b>フォールド</b>' in cleaned

    # CHECK-only pre-action is retained, but automatic CHECK/FOLD is gone.
    assert 'data-jj-preaction="check"' in cleaned
    assert "check_fold" not in cleaned
    assert "チェック / フォールド" not in cleaned

    start = cleaned.index("function jjV5MaybeRunPreAction")
    end = cleaned.index("function jjV5HotkeysEnabled")
    runner = cleaned[start:end]
    assert 'data-action="check"' in runner
    assert 'data-action="fold"' not in runner
    assert "jjV5PreAction.mode!=='check'" in runner

    # Telemetry must not retain a dead fast-fold choice either.
    assert "jjV6Emit('preaction','check')" in cleaned

    print("JJ_FAST_FOLD_REMOVED_OK")


if __name__ == "__main__":
    main()
