from __future__ import annotations

from pathlib import Path


def apply(root: Path) -> None:
    path = root / "static" / "app.js"
    text = path.read_text(encoding="utf-8")
    marker = "v1.24.0 isolated-runtime and action refinement"
    if marker in text:
        return

    mq_old = "const JJ_V124_DESKTOP_MQ=window.matchMedia('(min-width:761px)');"
    mq_new = """// v1.24.0 isolated-runtime and action refinement.\n  const JJ_V124_DESKTOP_MQ=(typeof window!=='undefined'&&typeof window.matchMedia==='function')\n    ? window.matchMedia('(min-width:761px)')\n    : {matches:false,addEventListener:()=>{}};"""
    if mq_old not in text:
        raise RuntimeError("v1.24 media query target missing")
    text = text.replace(mq_old, mq_new, 1)

    # If calling consumes the entire remaining stack, CALL and ALL-IN are not two
    # independent poker decisions. Present one explicit all-in call rather than
    # two buttons that perform the same commitment.
    call_old = "const callChips=Number(l.call_amount||0),callText=jjV124RawBb(callChips,{maxDecimals:1});"
    call_new = "const hero=jjV124Hero(),callChips=Number(l.call_amount||0),callText=jjV124RawBb(callChips,{maxDecimals:1}),callIsAllin=callChips>0&&callChips>=Number(hero?.stack||Infinity);"
    if call_old not in text:
        raise RuntimeError("v1.24 call action target missing")
    text = text.replace(call_old, call_new, 1)

    label_old = "actions.push(`<button class=\"jj-action-btn jj-call\" data-action=\"call\"><small>CALL</small><b>コール <span id=\"jjV124CallButtonAmount\">${safe(callText)}</span></b></button>`);"
    label_new = "actions.push(`<button class=\"jj-action-btn jj-call\" data-action=\"call\"><small>${callIsAllin?'ALL-IN CALL':'CALL'}</small><b>${callIsAllin?'オールインコール':'コール'} <span id=\"jjV124CallButtonAmount\">${safe(callText)}</span></b></button>`);"
    if label_old not in text:
        raise RuntimeError("v1.24 call label target missing")
    text = text.replace(label_old, label_new, 1)

    allin_old = """    }else if(l.can_all_in){\n      actions.push('<button class=\"jj-action-btn jj-allin\" data-action=\"allin\"><small>ALL-IN</small><b>オールイン</b></button>');\n    }"""
    allin_new = """    }else if(l.can_all_in&&!l.can_call){\n      actions.push('<button class=\"jj-action-btn jj-allin\" data-action=\"allin\"><small>ALL-IN</small><b>オールイン</b></button>');\n    }"""
    if allin_old not in text:
        raise RuntimeError("v1.24 duplicate all-in action target missing")
    text = text.replace(allin_old, allin_new, 1)

    path.write_text(text, encoding="utf-8")
