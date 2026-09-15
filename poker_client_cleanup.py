from __future__ import annotations

"""Narrow production-client cleanup for removed poker controls.

Phase 4B introduced a zero-chip pre-action that could automatically choose
CHECK or FOLD when the hero's turn arrived. The automatic fold path adds no
useful value for JJ Arena and is intentionally removed here while retaining the
manual FOLD button and the optional CHECK-only pre-action.
"""


def remove_fast_fold(source: str) -> str:
    value = source

    # Remove the check/fold reservation control from the waiting action bar.
    value = value.replace(
        '<button type="button" class="ghost ${mode===\'check_fold\'?\'is-selected\':\'\'}" data-jj-preaction="check_fold" aria-pressed="${mode===\'check_fold\'?\'true\':\'false\'}">チェック / フォールド</button>',
        '',
    )

    # Only CHECK remains a valid automatic pre-action.
    value = value.replace(
        "if(!['check','check_fold'].includes(mode))return;",
        "if(mode!=='check')return;",
    )

    old_runner = """    const mode=jjV5PreAction.mode,l=tableState.legal||{};
    let selector='';
    if(mode==='check'){
      if(!l.can_check){jjV5ClearPreAction('チェックできない状況になったため予約を解除しました');return}
      selector='#actionBar [data-action=\"check\"]';
    }else{
      selector=l.can_check?'#actionBar [data-action=\"check\"]':'#actionBar [data-action=\"fold\"]';
    }
"""
    new_runner = """    const l=tableState.legal||{};
    if(jjV5PreAction.mode!=='check'){jjV5ClearPreAction();return}
    if(!l.can_check){jjV5ClearPreAction('チェックできない状況になったため予約を解除しました');return}
    const selector='#actionBar [data-action=\"check\"]';
"""
    value = value.replace(old_runner, new_runner)

    # Telemetry accepts only the remaining CHECK reservation.
    value = value.replace(
        "if(pre&&['check','check_fold'].includes(pre.dataset.jjPreaction||''))jjV6Emit('preaction',pre.dataset.jjPreaction);",
        "if(pre&&pre.dataset.jjPreaction==='check')jjV6Emit('preaction','check');",
    )

    if "check_fold" in value or "チェック / フォールド" in value:
        raise RuntimeError("fast-fold cleanup drift: automatic check/fold remains in served client")
    return value


__all__ = ["remove_fast_fold"]
