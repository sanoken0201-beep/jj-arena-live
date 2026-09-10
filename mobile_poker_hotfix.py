from __future__ import annotations

from pathlib import Path


ASSET_VERSION_OLD = "48"
ASSET_VERSION_NEW = "48-hotfix1"


def apply(root: Path) -> None:
    _app(root / "static" / "app.js")
    _styles(root / "static" / "styles.css")
    _index(root / "static" / "index.html")
    _sw(root / "static" / "sw.js")


def _app(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    marker = "v1.20.3 mobile bet-marker/call-amount hotfix"
    if marker in text:
        return
    pos = text.rfind("})();")
    if pos < 0:
        raise RuntimeError("mobile poker hotfix app closing marker missing")

    addon = r'''

  // v1.20.3 mobile bet-marker/call-amount hotfix.
  // legal.call_amount is returned by the server in raw table chips. The older
  // mobile renderer formatted that raw integer as BB, so 2,500 chips at a
  // 100-chip big blind was shown as 2,500bb instead of 25bb. Keep the action
  // request unchanged and fix presentation through the existing raw-chip -> BB
  // converter used elsewhere in the table UI.
  if(typeof renderActionBar==='function'){
    const jjMobileHotfixRenderActionBar=renderActionBar;
    renderActionBar=function(){
      jjMobileHotfixRenderActionBar();
      const l=tableState?.legal||{};
      if(!l.can_act||l.can_check)return;
      const callLabel=bb(Number(l.call_amount||0));
      const callButton=$('#actionBar .jj-call b');
      if(callButton)callButton.textContent=`コール ${callLabel}`;
      const contextAmount=$('#actionBar .jj-action-context b');
      if(contextAmount&&Number(l.call_amount||0)>0)contextAmount.textContent=`コール額 ${callLabel}`;
    };
  }

  // Portrait geometry: the generic seat-to-center interpolation puts the hero
  // blind/bet marker directly over the enlarged hero hole cards and puts the
  // 12-o'clock marker too close to the community cards. Move only those two
  // high-risk positions; the four side seats retain the established geometry.
  if(typeof jjBetPos==='function' && typeof jjVisualIndex==='function'){
    const jjMobileHotfixBetPos=jjBetPos;
    jjBetPos=function(actual){
      const p=jjMobileHotfixBetPos(actual);
      if(!window.matchMedia('(max-width:760px) and (orientation:portrait)').matches)return p;
      const visual=jjVisualIndex(actual);
      if(visual===0)return {left:p.left,top:56.5};
      if(visual===3)return {left:p.left,top:27};
      return p;
    };
  }
'''
    path.write_text(text[:pos] + addon + text[pos:], encoding="utf-8")


def _styles(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    marker = "v1.20.3 mobile bet marker collision guard"
    if marker in text:
        return
    text += r'''

/* v1.20.3 mobile bet marker collision guard. Bet chips are informational and
   must never block card/table interactions if future geometry shifts again. */
@media (max-width:760px) and (orientation:portrait){
  body.jj-mobile-table-open #pokerRoom .jj-bet-marker{pointer-events:none!important}
}
'''
    path.write_text(text, encoding="utf-8")


def _index(path: Path) -> None:
    text = path.read_text(encoding="utf-8").replace(
        f"?v={ASSET_VERSION_OLD}", f"?v={ASSET_VERSION_NEW}"
    )
    path.write_text(text, encoding="utf-8")


def _sw(path: Path) -> None:
    text = path.read_text(encoding="utf-8").replace(
        f"jj-arena-live-v{ASSET_VERSION_OLD}",
        f"jj-arena-live-v{ASSET_VERSION_NEW}",
    )
    path.write_text(text, encoding="utf-8")
