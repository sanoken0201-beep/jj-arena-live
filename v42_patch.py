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
    text = text.replace('version="1.19.2"', 'version="1.19.3"')
    text = text.replace('"version":"1.19.2"', '"version":"1.19.3"')
    text = text.replace('request.url.query == "v=41"', 'request.url.query == "v=42"')
    path.write_text(text, encoding="utf-8")


def _app(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "v1.19.3 member PIN self-service" in text:
        return

    old_actions = '''<div class="profile-settings-divider"></div>\n      <div class="profile-settings-actions"><button class="soft" type="button" id="openMemberDirectory">メンバー一覧を見る</button><button class="ghost" type="button" id="openPinSettings">6桁PINを変更</button></div></div>`;'''
    new_actions = '''<div class="profile-settings-divider"></div>\n      <section class="jj-account-security"><div><div class="eyebrow">SECURITY</div><h4>ログインPIN</h4><p class="hint">ログインに使う6桁PINは、本人だけが現在のPINを使って変更できます。変更後は他端末のログインを解除します。</p></div><button class="primary" type="button" id="openPinSettings">PINを変更</button></section>\n      <div class="profile-settings-actions"><button class="soft" type="button" id="openMemberDirectory">メンバー一覧を見る</button></div></div>`;'''
    if old_actions not in text:
        raise RuntimeError("v1.19.3 profile security action marker missing")
    text = text.replace(old_actions, new_actions, 1)

    pattern = re.compile(
        r"  function openPinSettings\(\)\{.*?\n  \}\n  function updateProfileAvatarPreview\(\)\{",
        re.S,
    )
    replacement = r'''  function openPinSettings(){
    openModal(`<div class="jj-pin-change-shell"><div class="eyebrow">LOGIN SECURITY</div><h3>6桁PINを変更</h3><p class="hint">現在のPINを確認したうえで、新しいPINへ変更します。管理者を含め、現在のPINそのものを画面から読み出すことはできません。</p><form id="pinChangeConfirmForm" class="stack" autocomplete="off"><label>現在の6桁PIN<input name="current_pin" type="password" inputmode="numeric" pattern="[0-9]{6}" minlength="6" maxlength="6" autocomplete="current-password" required placeholder="••••••"></label><label>新しい6桁PIN<input name="new_pin" type="password" inputmode="numeric" pattern="[0-9]{6}" minlength="6" maxlength="6" autocomplete="new-password" required placeholder="••••••"></label><label>新しい6桁PIN（確認）<input name="confirm_pin" type="password" inputmode="numeric" pattern="[0-9]{6}" minlength="6" maxlength="6" autocomplete="new-password" required placeholder="••••••"></label><div class="jj-pin-change-note">変更後もこの端末ではログインを維持し、ほかの端末のセッションは失効します。</div><button class="primary">PINを変更</button></form></div>`);
  }
  function updateProfileAvatarPreview(){'''
    text, count = pattern.subn(replacement, text, count=1)
    if count != 1:
        raise RuntimeError(f"v1.19.3 PIN settings function replacement mismatch: {count}")

    marker = "})();"
    pos = text.rfind(marker)
    if pos < 0:
        raise RuntimeError("v1.19.3 app closing marker missing")
    addon = r'''

  // v1.19.3 member PIN self-service.
  // Use a dedicated form id so the older two-field handler cannot submit before
  // the confirmation field is checked.
  document.addEventListener('submit',async event=>{
    if(event.target.id!=='pinChangeConfirmForm')return;
    event.preventDefault();
    event.stopImmediatePropagation();
    const form=event.target,fd=new FormData(form),button=event.submitter;
    const current=String(fd.get('current_pin')||'').trim();
    const next=String(fd.get('new_pin')||'').trim();
    const confirmPin=String(fd.get('confirm_pin')||'').trim();
    if(!/^\d{6}$/.test(current)||!/^\d{6}$/.test(next)||!/^\d{6}$/.test(confirmPin))return toast('PINは6桁の数字で入力してください');
    if(next!==confirmPin)return toast('新しいPINが一致しません');
    if(current===next)return toast('現在と異なるPINを設定してください');
    try{
      if(button){button.disabled=true;button.textContent='変更中…'}
      await post('/auth/change-pin',{current_pin:current,new_pin:next});
      form.reset();
      closeModal();
      toast('PINを変更しました');
    }catch(err){toast(err.message)}
    finally{if(button){button.disabled=false;button.textContent='PINを変更'}}
  },true);
'''
    text = text[:pos] + addon + text[pos:]
    path.write_text(text, encoding="utf-8")


def _styles(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "v1.19.3 member PIN self-service" in text:
        return
    text += r'''

/* v1.19.3 member PIN self-service */
.jj-account-security{display:flex;align-items:center;justify-content:space-between;gap:18px;padding:16px;border:1px solid rgba(242,205,99,.28);border-radius:15px;background:rgba(242,205,99,.055)}
.jj-account-security h4{margin:.2rem 0 .25rem;font-size:.95rem}.jj-account-security p{margin:0;max-width:520px;line-height:1.55}.jj-account-security>button{flex:0 0 auto;min-width:118px}
.jj-pin-change-shell{width:min(480px,100%)}.jj-pin-change-shell h3{margin:.2rem 0 .35rem}.jj-pin-change-note{padding:10px 12px;border-radius:11px;background:rgba(90,166,129,.08);color:var(--muted,#68756f);font-size:.73rem;line-height:1.5}
#pinChangeConfirmForm input{letter-spacing:.22em;font-variant-numeric:tabular-nums}
@media(max-width:760px){.jj-account-security{align-items:stretch;flex-direction:column}.jj-account-security>button{width:100%}}
'''
    path.write_text(text, encoding="utf-8")


def _index(path: Path) -> None:
    text = path.read_text(encoding="utf-8").replace("?v=41", "?v=42")
    path.write_text(text, encoding="utf-8")


def _sw(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"jj-arena-live-v\d+", "jj-arena-live-v42", text)
    path.write_text(text, encoding="utf-8")
