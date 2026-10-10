/* Season metadata admin panel. The active ranking window is not switched here. */
(() => {
  const $ = selector => document.querySelector(selector);
  const form = $('#seasonCreateForm');
  const list = $('#seasonList');
  if (!form || !list) return;
  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({
    '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'
  })[char]);
  const toDay = value => new Date(value + 'T00:00:00Z');
  const offsetDay = (value, amount) => {
    const day=toDay(value);
    if (!Number.isFinite(day.getTime())) return value;
    day.setUTCDate(day.getUTCDate() + amount);
    return day.toISOString().slice(0,10);
  };
  const showError = message => {
    const toast = $('#toast');
    if (!toast) return window.alert(message);
    toast.textContent=message;
    toast.classList.add('show');
    setTimeout(()=>toast.classList.remove('show'),3500);
  };
  const json = async (url, options) => {
    const response = await fetch(url, {
      credentials:'include', cache:'no-store',
      headers: {'Content-Type':'application/json'},
      ...(options||{})
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'HTTP ' + response.status);
    return data;
  };
  const statusLabel = {active:'集計中',archived:'過去',draft:'準備中'};
  function render(items) {
    list.innerHTML = items.map(item => {
      const locked=Boolean(Number(item.locked_bounds));
      const start = item.start_date === '0000-01-01' ? '過去全期間' : item.start_date;
      const last = offsetDay(item.end_exclusive, -1);
      const fields = locked
        ? '<p class="field-note">期間：'+escapeHtml(start)+' 〜 '+escapeHtml(last)+'（変更不可）</p>'
        : '<label>開始日<input type="date" name="start_date" value="'+escapeHtml(item.start_date)+'" required></label>'
          +'<label>終了日（含む）<input type="date" name="end_date" value="'+escapeHtml(last)+'" required></label>';
      return '<form class="form-stack seasonEditForm" data-id="'+escapeHtml(item.season_id)+'" style="padding:16px 0;border-bottom:1px solid rgba(128,128,128,.25)">'
        +'<div class="eyebrow">'+escapeHtml(statusLabel[item.status]||item.status)+' / '+escapeHtml(item.season_id)+'</div>'
        +'<label>表示名<input name="name" maxlength="80" value="'+escapeHtml(item.name)+'" required></label>'
        +fields
        +'<button class="soft" type="submit">このシーズンの設定を保存</button></form>';
    }).join('') || '<div class="empty-state">登録済みシーズンはありません</div>';
  }
  async function load() {
    const items = await json('/api/admin/console/seasons');
    render(items);
    const current = items.find(item => item.status==='active');
    const nextStart = current?.end_exclusive || '2027-04-01';
    if (!form.elements.start_date.value) form.elements.start_date.value=nextStart;
    if (!form.elements.end_date.value) form.elements.end_date.value=offsetDay(offsetDay(nextStart,180),-1);
    return items;
  }
  window.jjLoadSeasons=() => load().catch(error => showError(error.message));
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const button=form.querySelector('button[type="submit"]');
    if (button.disabled) return;
    const body={
      name:form.elements.name.value.trim(),
      start_date:form.elements.start_date.value,
      end_exclusive:offsetDay(form.elements.end_date.value,1)
    };
    if (!window.confirm('「'+body.name+'」を準備中として登録します。ランキングの切替は実施しません。')) return;
    button.disabled=true;
    try {
      await json('/api/admin/console/seasons',{
        method:'POST',body:JSON.stringify(body)
      });
      form.reset();
      await load();
      showError('次期シーズンの予定を保存しました');
    } catch(error) { showError(error.message); }
    finally { button.disabled=false; }
  });
  list.addEventListener('submit', async event => {
    const edit=event.target.closest('.seasonEditForm');
    if (!edit) return;
    event.preventDefault();
    const button=edit.querySelector('button[type="submit"]');
    if (button.disabled) return;
    const body={name:edit.elements.name.value.trim()};
    if (edit.elements.start_date) {
      body.start_date=edit.elements.start_date.value;
      body.end_exclusive=offsetDay(edit.elements.end_date.value,1);
    }
    if (!window.confirm('シーズン設定を保存します。確定済みポイント履歴は変更しません。')) return;
    button.disabled=true;
    try {
      await json('/api/admin/console/seasons/'+encodeURIComponent(edit.dataset.id),{
        method:'PATCH',body:JSON.stringify(body)
      });
      await load();
      showError('シーズンの設定を保存しました');
    } catch(error) { showError(error.message); button.disabled=false; }
  });
})();