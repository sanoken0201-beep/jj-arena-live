/* Additive, PIN-confirmed administrator grants in the canonical account dialog. */
(() => {
  const body = document.getElementById('userDialogBody');
  if (!body) return;

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
    if (!content || !form || content.querySelector('[data-admin-grant]')) return;
    const uid = Number(form.dataset.userId);
    const role = body.querySelector('.dialog-meta')?.textContent?.trim().split(' ')[0]?.toLowerCase();
    if (!Number.isSafeInteger(uid) || uid <= 0 || !['admin', 'member'].includes(role)) return;

    const container = document.createElement('div');
    container.className = 'form-stack';
    container.dataset.adminGrant = '1';
    if (role === 'admin') {
      container.innerHTML = '<h4>管理者権限</h4>'
        + '<p class="field-note">このアカウントは管理者です。管理者の引継ぎは追加方式のため、既存管理者の権限やアカウント、ポイント・履歴は失効しません。</p>';
    } else {
      container.innerHTML = '<h4>管理者を追加（権限の引継ぎ）</h4>'
        + '<p class="field-note">引継ぎは管理者の追加です。現在の管理者の権限・ログイン、双方のポイント・ランキング・対戦履歴はそのまま残ります。</p>'
        + '<form id="roleDelegationForm" class="form-stack">'
        + '<label>操作中の管理者の6桁PIN<input name="current_pin" type="password" autocomplete="off" inputmode="numeric" pattern="[0-9]{6}" minlength="6" maxlength="6" required></label>'
        + '<p class="field-note">追加先はJJメンバー本人確認済みの有効アカウントに限ります。追加先のみ、安全のため全端末で再ログインが必要になります。</p>'
        + '<button class="primary" type="submit">この会員を管理者に追加</button></form>';
      container.querySelector('form').addEventListener('submit', async event => {
        event.preventDefault();
        const panel = event.currentTarget;
        if (panel.dataset.pending) return;
        const pin = panel.elements.current_pin.value;
        if (!/^[0-9]{6}$/.test(pin)) return showMessage('6桁のPINを入力してください');
        const name = body.querySelector('.dialog-inner h3')?.textContent?.trim() || '対象者';
        if (!window.confirm(name + 'を管理者に追加します。既存管理者の権限とデータは保持され、追加先のみ再ログインが必要です。続行しますか？')) return;
        panel.dataset.pending = '1';
        const button = panel.querySelector('button[type="submit"]');
        button.disabled = true;
        try {
          const response = await fetch('/api/admin/console/users/' + uid + '/role', {
            method: 'POST',
            credentials: 'include',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({role: 'admin', current_pin: pin})
          });
          const result = await response.json().catch(() => ({}));
          if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'HTTP ' + response.status);
          window.location.reload();
        } catch (error) {
          panel.elements.current_pin.value = '';
          showMessage(error.message);
        } finally {
          delete panel.dataset.pending;
          button.disabled = false;
        }
      });
    }
    const divider = document.createElement('hr');
    divider.className = 'divider';
    divider.style.cssText = 'margin:16px 0;border:0;border-top:1px solid currentColor;opacity:.18';
    content.append(divider, container);
  }

  const observer = new MutationObserver(augment);
  observer.observe(body, {childList: true});
  augment();
})();
