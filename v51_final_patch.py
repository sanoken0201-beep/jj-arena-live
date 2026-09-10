from __future__ import annotations

from pathlib import Path


def apply(root: Path) -> None:
    _server(root / "server.py")
    _app(root / "static" / "app.js")
    _styles(root / "static" / "styles.css")


def _server(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    marker = "v1.23.0 forced-runout operational logging"
    if marker in text:
        return
    old = '''                except Exception:\n                    # A transient table read/broadcast problem must not stop the\n                    # normal auto-deal lifecycle for every other table.\n                    continue'''
    new = '''                except Exception as exc:\n                    # v1.23.0 forced-runout operational logging. A single table\n                    # must not stop the lifecycle, but a stuck staged runout must\n                    # remain diagnosable from the existing operations error log.\n                    import resilience as _jj_v123_resilience\n                    _jj_v123_resilience.record_error(\n                        db,\n                        "forced_runout",\n                        f"{type(exc).__name__}: {exc}",\n                        path=table_id,\n                    )\n                    continue'''
    if old not in text:
        raise RuntimeError("v1.23 forced-runout error handler target missing")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def _app(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    marker = "v1.23.0 final mobile interaction audit"
    if marker in text:
        return

    # Bind an armed all-in confirmation to the exact hand/turn/action/amount.
    old_state = "  let jjV123AllinConfirmUntil=0;"
    new_state = '''  // v1.23.0 final mobile interaction audit.\n  let jjV123AllinConfirmUntil=0;\n  let jjV123AllinConfirmKey='';\n\n  function jjV123AllinKey(action,selected){\n    const hand=tableState?.hand||{};\n    return `${hand.id||''}:${hand.action_seat??''}:${action}:${Number(selected||0).toFixed(2)}`;\n  }'''
    if old_state not in text:
        raise RuntimeError("v1.23 all-in confirmation state target missing")
    text = text.replace(old_state, new_state, 1)

    old_confirm = '''    const now=Date.now();\n    if(jjV123AllinConfirmUntil<now){\n      e.preventDefault();e.stopImmediatePropagation();\n      jjV123AllinConfirmUntil=now+2600;\n      btn.classList.add('jj-confirm-allin');'''
    new_confirm = '''    const now=Date.now(),confirmKey=jjV123AllinKey(action,selected);\n    if(jjV123AllinConfirmUntil<now||jjV123AllinConfirmKey!==confirmKey){\n      e.preventDefault();e.stopImmediatePropagation();\n      jjV123AllinConfirmUntil=now+2600;\n      jjV123AllinConfirmKey=confirmKey;\n      btn.classList.add('jj-confirm-allin');'''
    if old_confirm not in text:
        raise RuntimeError("v1.23 all-in confirmation block target missing")
    text = text.replace(old_confirm, new_confirm, 1)
    old_reset = "    jjV123AllinConfirmUntil=0;\n  },true);"
    new_reset = "    jjV123AllinConfirmUntil=0;jjV123AllinConfirmKey='';\n  },true);"
    if old_reset not in text:
        raise RuntimeError("v1.23 all-in confirmation reset target missing")
    text = text.replace(old_reset, new_reset, 1)

    # On touch devices a title tooltip is not a usable explanation. Render the
    # most relevant unavailable-action reasons directly below the status row.
    old_reasons = '''    bar.querySelectorAll('button:disabled').forEach(btn=>{\n      if(!btn.title)btn.title='現在この操作はできません';\n    });\n  }'''
    new_reasons = '''    bar.querySelectorAll('button:disabled').forEach(btn=>{\n      if(!btn.title)btn.title='現在この操作はできません';\n    });\n\n    const hintItems=[];\n    if(l.can_act&&!l.can_raise&&reasons.raise)hintItems.push(`レイズ不可：${reasons.raise}`);\n    if(l.can_act&&l.can_check&&reasons.fold)hintItems.push('Foldは誤操作防止で非表示：Checkで無料に続行できます');\n    let hints=$('#jjV123DisabledHints',bar);\n    if(hintItems.length){\n      if(!hints){\n        status?.insertAdjacentHTML('afterend','<div id="jjV123DisabledHints" class="jj-v123-disabled-hints" aria-live="polite"></div>');\n        hints=$('#jjV123DisabledHints',bar);\n      }\n      if(hints)hints.innerHTML=hintItems.map(x=>`<span>${safe(x)}</span>`).join('');\n    }else if(hints){hints.remove()}\n  }'''
    if old_reasons not in text:
        raise RuntimeError("v1.23 disabled reason UI target missing")
    text = text.replace(old_reasons, new_reasons, 1)

    # Turn the numeric clock into a glanceable shrinking progress meter while
    # retaining exact seconds and the existing 10-second sound/haptic warning.
    old_clock_start = '''  function jjV123ClockFeedback(){\n    const deadline=tableState?.hand?.action_deadline,l=tableState?.legal||{};\n    if(!deadline||!l.can_act){jjV123ClockWarnedFor='';return}\n    const sec=Math.max(0,Math.ceil((new Date(deadline)-new Date())/1000));'''
    new_clock_start = '''  function jjV123ClockFeedback(){\n    const deadline=tableState?.hand?.action_deadline,l=tableState?.legal||{},clock=$('#jjActionClock');\n    if(!deadline||!l.can_act){\n      jjV123ClockWarnedFor='';\n      if(clock){clock.style.removeProperty('--jj-v123-clock-pct');clock.removeAttribute('aria-label')}\n      return\n    }\n    const sec=Math.max(0,Math.ceil((new Date(deadline)-new Date())/1000));\n    if(clock){\n      const pct=Math.max(0,Math.min(100,(sec/45)*100));\n      clock.style.setProperty('--jj-v123-clock-pct',`${pct}%`);\n      clock.setAttribute('aria-label',`アクション残り${sec}秒`);\n    }'''
    if old_clock_start not in text:
        raise RuntimeError("v1.23 action clock target missing")
    text = text.replace(old_clock_start, new_clock_start, 1)

    # Browser online/offline is not enough: a WebSocket can be reconnecting while
    # HTTP polling keeps the table usable. Surface that state without blocking play.
    insertion = '''\n  function jjV123ConnectionState(){\n    if(typeof document==='undefined')return;\n    const room=$('#pokerRoom');if(!room)return;\n    let badge=$('#jjV123TableConnection',room);\n    const offline=typeof navigator!=='undefined'&&navigator.onLine===false;\n    const hasSocket=typeof WebSocket!=='undefined'&&typeof tableWS!=='undefined'&&!!tableWS;\n    const open=hasSocket&&tableWS.readyState===WebSocket.OPEN;\n    const connecting=hasSocket&&tableWS.readyState===WebSocket.CONNECTING;\n    const show=!!currentTableId&&!offline&&hasSocket&&!open;\n    if(!show){if(badge)badge.remove();return}\n    if(!badge){\n      room.insertAdjacentHTML('afterbegin','<div id="jjV123TableConnection" class="jj-v123-table-connection" role="status" aria-live="polite"></div>');\n      badge=$('#jjV123TableConnection',room);\n    }\n    if(badge)badge.textContent=connecting?'接続中…':'再接続中 · 卓の更新を継続中';\n  }\n'''
    anchor = "\n  const jjV123BaseRenderActionBar=typeof renderActionBar==='function'?renderActionBar:null;"
    if anchor not in text:
        raise RuntimeError("v1.23 connection-state insertion anchor missing")
    text = text.replace(anchor, insertion + anchor, 1)

    old_render = '''    jjV123ClockFeedback();\n    document.body.classList.toggle('jj-v123-hero-turn',!!tableState?.legal?.can_act&&!jjV123Pending());'''
    new_render = '''    jjV123ClockFeedback();\n    jjV123ConnectionState();\n    document.body.classList.toggle('jj-v123-hero-turn',!!tableState?.legal?.can_act&&!jjV123Pending());'''
    if old_render not in text:
        raise RuntimeError("v1.23 poker render connection target missing")
    text = text.replace(old_render, new_render, 1)

    old_timer = "if(typeof window!=='undefined'&&typeof renderPokerRoom==='function')window.setInterval(()=>{jjV123ClockFeedback();jjV123ActionState()},500);"
    new_timer = "if(typeof window!=='undefined'&&typeof renderPokerRoom==='function')window.setInterval(()=>{jjV123ClockFeedback();jjV123ActionState();jjV123ConnectionState()},500);"
    if old_timer not in text:
        raise RuntimeError("v1.23 final status timer target missing")
    text = text.replace(old_timer, new_timer, 1)

    path.write_text(text, encoding="utf-8")


def _styles(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    marker = "v1.23.0 final mobile interaction audit"
    if marker in text:
        return
    addon = r'''

/* v1.23.0 final mobile interaction audit */
#actionBar .jj-v123-disabled-hints{display:flex;flex-wrap:wrap;justify-content:center;gap:4px 8px;margin:-2px 0 7px;color:#aebdb6;font-size:.62rem;line-height:1.35;text-align:center}
#actionBar .jj-v123-disabled-hints span{display:inline-flex;align-items:center;min-height:22px;padding:2px 7px;border-radius:999px;background:rgba(255,255,255,.045);border:1px solid rgba(255,255,255,.07)}
#actionBar .jj-action-clock{--jj-v123-clock-pct:100%;background:linear-gradient(90deg,rgba(231,190,83,.24) 0 var(--jj-v123-clock-pct),rgba(255,255,255,.055) var(--jj-v123-clock-pct) 100%)!important}
#actionBar .jj-action-clock.is-urgent{background:linear-gradient(90deg,rgba(198,66,66,.42) 0 var(--jj-v123-clock-pct),rgba(181,66,66,.13) var(--jj-v123-clock-pct) 100%)!important}
.jj-v123-table-connection{position:fixed;z-index:140;top:calc(env(safe-area-inset-top) + 51px);right:8px;max-width:min(240px,calc(100vw - 16px));padding:5px 9px;border-radius:999px;background:rgba(30,50,62,.94);border:1px solid rgba(111,183,226,.42);color:#d9f1ff;font-size:.61rem;font-weight:850;line-height:1.2;box-shadow:0 6px 16px rgba(0,0,0,.28);pointer-events:none}
@media(max-width:760px){
  body.jj-mobile-table-open #actionBar .jj-v123-disabled-hints{font-size:.59rem;margin-bottom:6px}
  body.jj-mobile-table-open #actionBar .jj-v123-disabled-hints span{min-height:24px;padding-inline:6px}
}
'''
    path.write_text(text.rstrip() + addon + "\n", encoding="utf-8")
