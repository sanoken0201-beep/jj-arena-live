/* PIN-confirmed administrator delegation in the canonical account dialog. */
(() => {
  const body = document.getElementById('userDialogBody');
  if (!body) return;
  let myId = null;
  fetch('/api/me', {credentials:'include', cache:'no-store'})
    .then(r => r.ok ? r.json() : null).then(me => { if(me) myId = Number(me.id); })
    .catch(() => {});

  function showMessage(message) {
    const toast = document.getElementById('toast');
    if (!toast) return window.alert(message);
    toast.textContent = message;
    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), 3500);
  }

  function augment() {
    const content = body.querySelector('.dialog-inner');
    const form = body.querySelector('#userEditForm');
    if (!content || !form || body.querySelector('#roleDelegationForm')) return;
    const uid = Number(form.dataset.userId);
    const role = body.querySelector('.dialog-meta')?.textContent?.trim().split(' ')[0]?.toLowerCase();
    if (!Number.isSafeInteger(uid) || uid <= 0 || !['admin','member'].includes(role)) return;

    const container = document.createElement('div');
    container.className = 'form-stack';
    if (myId !== null && myId === uid) {
      container.innerHTML = '<p class="field-note">自分自身の管理者権限は変更できません。権限の解除は後任の管理者から実施してください。</p>';
    } else {
      container.innerHTML = '<h4>管理者権限の引き継ぎ</h4>'
        + '<form id="roleDelegationForm" class="form-stack">'
        + '<label>変更後の権限<select name="role" required>'
        + '<option value="member">一般会員</option><option value="admin">管理者</option>'
        + '</select></label>'
        + '<label>操作中の管理者の6桁PIN<input name="current_pin" type="password" autocomplete="off" inputmode="numeric" pattern="[0-9]{6}" minlength="6" maxlength="6" required></label>'
        + '<p class="field-note">管理者への任命にはJJメンバー本人確認が必要です。変更後、対象者の全セッションを失効します。</p>'
        + '<button class="primary" type="submit">権限を変更する</button></form>';
      const newRole = container.querySelector('[name="role"]');
      newRole.value = role;
      container.querySelector('form').addEventListener('submit', async event => {
        event.preventDefault();
        const panel = event.currentTarget;
        if (panel.dataset.pending) return;
        const roleToSet = newRole.value;
        if (roleToSet === role) return showMessage('現在と同じ権限です');
        const pin = panel.elements.current_pin.value;
        if (!/^[0-9]{6}$/.test(pin)) return showMessage('6桁のPINを入力してください');
        const name = body.querySelector('.dialog-inner h3')?.textContent?.trim() || '対象者';
        if (!window.confirm(name + 'の権限を' + (roleToSet==='admin'?'管理者に変更':'一般会員に変更') + 'し、対象者を全端末からログアウトさせます。続行しますか？')) return;
        panel.dataset.pending='1';
        const button = panel.querySelector('button[type="submit"]');
        button.disabled = true;
        try {
          const response = await fetch('/api/admin/console/users/' + uid + '/role', {
            method: 'POST',
            credentials: 'include',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({role:roleToSet,current_pin:pin})
          });
          const result = await response.json().catch(() => ({}));
          if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'HTTP ' + response.status);
          window.location.reload();
        } catch (error) {
          panel.elements.current_pin.value='';
          showMessage(error.message);
        } finally {
          delete panel.dataset.pending;
          button.disabled = false;
        }
      });
    }
    const divider = document.createElement('hr');
    divider.className = 'divider';
    divider.style.cssText='margin:16px 0;border:0;border-top:1px solid currentColor;opacity:.18';
    content.append(divider, container);
  }

  const observer = new MutationObserver(augment);
  observer.observe(body,{childList:true});
  augment();
})();