from __future__ import annotations

import re
from pathlib import Path


def apply(root: Path) -> None:
    _server(root / "server.py")
    _app(root / "static" / "app.js")
    _styles(root / "static" / "styles.css")
    _index(root / "static" / "index.html")
    _sw(root / "static" / "sw.js")


def _server(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = text.replace('version="1.19.3"', 'version="1.19.4"')
    text = text.replace('"version":"1.19.3"', '"version":"1.19.4"')
    text = text.replace('request.url.query == "v=42"', 'request.url.query == "v=43"')
    path.write_text(text, encoding="utf-8")


def _app(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "v1.19.4 UI foundation and accessibility" in text:
        return

    marker = "})();"
    pos = text.rfind(marker)
    if pos < 0:
        raise RuntimeError("v1.19.4 app closing marker missing")

    addon = r'''

  // v1.19.4 UI foundation and accessibility.
  // This layer is deliberately presentation-only: no ranking, points, auth,
  // tournament, or poker-engine semantics are changed here.
  let jjV194ConnectionNode=null;

  function jjV194EnsureConnectionStatus(){
    if(jjV194ConnectionNode?.isConnected)return jjV194ConnectionNode;
    let node=document.getElementById('jjConnectionStatus');
    if(!node){
      node=document.createElement('div');
      node.id='jjConnectionStatus';
      node.className='jj-connection-status';
      node.setAttribute('role','status');
      node.setAttribute('aria-live','polite');
      node.hidden=true;
      document.body.appendChild(node);
    }
    jjV194ConnectionNode=node;
    return node;
  }

  function jjV194UpdateConnectionStatus(){
    const node=jjV194EnsureConnectionStatus();
    const offline=navigator.onLine===false;
    node.hidden=!offline;
    node.textContent=offline?'オフラインです。接続が戻るまで操作結果は確定しない場合があります。':'';
    document.documentElement.classList.toggle('jj-is-offline',offline);
  }

  function jjV194EnhanceDom(root=document){
    document.documentElement.lang='ja';
    const toast=document.getElementById('toast');
    if(toast){
      toast.setAttribute('role','status');
      toast.setAttribute('aria-live','polite');
      toast.setAttribute('aria-atomic','true');
    }
    const login=document.getElementById('pinForm');
    if(login)login.setAttribute('aria-describedby','authMessage');
    const loginName=document.getElementById('loginName');
    if(loginName){
      loginName.setAttribute('autocapitalize','none');
      loginName.setAttribute('spellcheck','false');
      loginName.setAttribute('enterkeyhint','next');
    }
    const loginPin=document.getElementById('loginPin');
    if(loginPin)loginPin.setAttribute('enterkeyhint','go');
    const account=document.getElementById('accountBtn');
    if(account&&!account.getAttribute('aria-label'))account.setAttribute('aria-label','アカウント設定を開く');
    const actionBar=document.getElementById('actionBar');
    if(actionBar){
      actionBar.setAttribute('role','region');
      actionBar.setAttribute('aria-label','ポーカー操作');
    }
    const quiz=document.getElementById('quizChoices');
    if(quiz){
      quiz.setAttribute('role','group');
      quiz.setAttribute('aria-label','クイズの回答候補');
    }
    root.querySelectorAll?.('a[target="_blank"]').forEach(link=>{
      const rel=new Set(String(link.getAttribute('rel')||'').split(/\s+/).filter(Boolean));
      rel.add('noopener');rel.add('noreferrer');
      link.setAttribute('rel',[...rel].join(' '));
    });
    root.querySelectorAll?.('button[disabled],input[disabled],select[disabled],textarea[disabled]').forEach(el=>el.setAttribute('aria-disabled','true'));
  }

  function jjV194Boot(){
    jjV194EnhanceDom(document);
    jjV194UpdateConnectionStatus();
    window.addEventListener('online',jjV194UpdateConnectionStatus,{passive:true});
    window.addEventListener('offline',jjV194UpdateConnectionStatus,{passive:true});
    const observer=new MutationObserver(records=>{
      for(const record of records){
        for(const node of record.addedNodes){
          if(node?.nodeType===1)jjV194EnhanceDom(node);
        }
      }
    });
    observer.observe(document.body,{childList:true,subtree:true});
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',jjV194Boot,{once:true});
  else jjV194Boot();
'''
    text = text[:pos] + addon + text[pos:]
    path.write_text(text, encoding="utf-8")


def _styles(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "v1.19.4 UI foundation and accessibility" in text:
        return
    text += r'''

/* v1.19.4 UI foundation and accessibility */
:where(button,a,input,select,textarea,[tabindex]):focus-visible{outline:3px solid rgba(224,178,67,.72);outline-offset:3px}
:where(button,input,select,textarea):disabled{cursor:not-allowed;opacity:.58}
:where(.card,.panel,.profile-card,.jj-study-card,.jj-video-card){overflow-wrap:anywhere}
dialog{max-height:min(92dvh,860px);overflow:auto;overscroll-behavior:contain}
.jj-connection-status{position:fixed;z-index:9999;left:50%;bottom:max(14px,env(safe-area-inset-bottom));transform:translateX(-50%);width:min(620px,calc(100% - 28px));padding:10px 14px;border:1px solid rgba(217,151,52,.38);border-radius:12px;background:rgba(40,31,16,.96);color:#fff7df;box-shadow:0 12px 36px rgba(0,0,0,.22);font-size:.76rem;line-height:1.45;text-align:center}
.jj-connection-status[hidden]{display:none!important}
@media(max-width:760px){
  :where(button,.primary,.soft,.ghost,input,select,textarea){min-height:44px}
  :where(input,select,textarea){font-size:16px}
  #quizChoices button{min-height:48px}
  #actionBar button{min-height:48px}
  dialog{width:calc(100% - 20px);max-height:90dvh}
}
@media(prefers-reduced-motion:reduce){
  *,*::before,*::after{scroll-behavior:auto!important;animation-duration:.01ms!important;animation-iteration-count:1!important;transition-duration:.01ms!important}
}
'''
    path.write_text(text, encoding="utf-8")


def _index(path: Path) -> None:
    text = path.read_text(encoding="utf-8").replace("?v=42", "?v=43")
    path.write_text(text, encoding="utf-8")


def _sw(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"jj-arena-live-v\d+", "jj-arena-live-v43", text)
    path.write_text(text, encoding="utf-8")
