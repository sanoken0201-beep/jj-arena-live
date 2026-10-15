/* Lazy, admin-only JJ MDA population grid. NO polling or gameplay listeners. */
(() => {
  'use strict';
  const view = document.getElementById('mdaView');
  if (!view) return;
  const el = id => document.getElementById(id);
  const order = 'AKQJT98765432';
  const positionsBySize = {
    2: ['BTN/SB','BB'],
    3: ['BTN','SB','BB'],
    4: ['BTN','SB','BB','CO'],
    5: ['BTN','SB','BB','UTG','CO'],
    6: ['BTN','SB','BB','UTG','HJ','CO']
  };
  let requestVersion = 0;
  let lastKey = null;
  function wantedKey() {
    return [el('mdaGame').value, el('mdaSize').value, el('mdaPosition').value].join(':');
  }
  function setPositions() {
    const n = Number(el('mdaSize').value);
    const previous = el('mdaPosition').value;
    el('mdaPosition').replaceChildren(...positionsBySize[n].map(p => {
      const node = document.createElement('option');
      node.value = p;
      node.textContent = p;
      return node;
    }));
    if (positionsBySize[n].includes(previous)) el('mdaPosition').value = previous;
    else el('mdaPosition').value = n === 2 ? 'BTN/SB' : 'BTN';
  }
  function clearGrid() {
    el('mdaMatrix').replaceChildren();
  }
  function show(text) {
    el('mdaMessage').textContent = text;
  }
  function cardTitle(cell) {
    if (cell.status === 'observed') {
      const n = Number(cell.opportunities || 0);
      return cell.class + '：観測 ' + cell.open_frequency + '%、' + n + '機会';
    }
    if (cell.status === 'hypothesis') {
      return cell.class + '：' + (cell.hypothesis || '') + 'に基づく未観測の推定候補';
    }
    return cell.class + '：不明・サンプル不足';
  }
  function render(doc) {
    const data = doc.grid;
    if (!Array.isArray(data) || data.length !== 13 ||
        data.some(row => !Array.isArray(row) || row.length !== 13)) {
      show('データ形式が不正です。管理者に確認してください。');
      clearGrid();
      return;
    }
    const fragment = document.createDocumentFragment();
    for (let i = 0; i < 13; i++) {
      for (let j = 0; j < 13; j++) {
        const cell = data[i][j];
        const item = document.createElement('div');
        const expected = i === j ? order[i] + order[i] :
          i < j ? order[i] + order[j] + 's' : order[j] + order[i] + 'o';
        if (!cell || cell.class !== expected ||
            !['observed','hypothesis','unknown'].includes(cell.status)) {
          show('レンジ表の配置が正しくありません。');
          clearGrid();
          return;
        }
        item.className = 'mda-cell mda-' + cell.status;
        item.setAttribute('role', 'gridcell');
        item.setAttribute('aria-label', cardTitle(cell));
        const name = document.createElement('strong');
        name.textContent = expected;
        const line = document.createElement('span');
        if (cell.status === 'observed') {
          const f = Number(cell.open_frequency);
          if (!Number.isFinite(f) || f < 0 || f > 100) {
            show('観測値に不正なデータがあります。'); clearGrid(); return;
          }
          item.style.setProperty('--mda-heat', String(0.12 + f / 100 * 0.72));
          item.style.setProperty('--mda-border', String(0.17 + f / 100 * 0.30));
          if (f >= 65) item.classList.add('mda-observed-strong');
          line.textContent = f.toLocaleString('ja-JP',{maximumFractionDigits:1}) + '%';
        } else if (cell.status === 'hypothesis') {
          line.textContent = '推定';
        } else {
          line.textContent = '—';
        }
        item.append(name, line);
        fragment.appendChild(item);
      }
    }
    el('mdaMatrix').replaceChildren(fragment);
    const date = new Date(doc.generated_at);
    const stamp = Number.isFinite(date.valueOf()) ?
      date.toLocaleString('ja-JP', {timeZone:'Asia/Tokyo'}) : '時刻不明';
    const accepted = Number(doc.completed_hands_used || 0);
    show('更新：' + stamp + '（日本時間） · 完了ハンド ' + accepted.toLocaleString('ja-JP') +
      '件 · ' + (doc.range_status === 'ok' ? '集計可能' :
        doc.range_status === 'not_applicable' ? 'この位置でRFIは定義されません' :
        'サンプル不足のため公開可能な頻度なし'));
  }
  async function load(force = false) {
    if (!view.classList.contains('active-view')) return;
    const key = wantedKey();
    if (!force && key === lastKey) return;
    lastKey = key;
    const version = ++requestVersion;
    show('保存済みの集計データを読み込んでいます。');
    clearGrid();
    const params = new URLSearchParams({
      game: el('mdaGame').value, table_size: el('mdaSize').value,
      position: el('mdaPosition').value
    });
    try {
      const res = await fetch('/api/admin/mda/grid?' + params, {
        credentials: 'same-origin', cache: 'no-store',
        headers: {'Accept':'application/json'}
      });
      if (version !== requestVersion || !view.classList.contains('active-view')) return;
      if (res.status === 401 || res.status === 403) {
        show('管理者としてのログインが必要です。'); return;
      }
      if (!res.ok) {
        show('データの取得に失敗しました。接続を確認してください。'); return;
      }
      const data = await res.json();
      if (version !== requestVersion) return;
      if (data.status === 'not_ready') {
        show('分析スナップショットはまだありません。公開前のデータは表示しません。'); return;
      }
      if (data.status !== 'ok' || data.game !== el('mdaGame').value ||
          String(data.table_size) !== el('mdaSize').value ||
          data.position !== el('mdaPosition').value) {
        show('受信した分析データの対象が一致しません。'); return;
      }
      render(data);
    } catch (_) {
      if (version === requestVersion) show('通信エラーが発生しました。');
    }
  }
  setPositions();
  el('mdaSize').addEventListener('change', () => {setPositions();load(true);});
  el('mdaGame').addEventListener('change', () => load(true));
  el('mdaPosition').addEventListener('change', () => load(true));
  el('mdaRefresh').addEventListener('click', () => load(true));
  const observer = new MutationObserver(() => {
    if (view.classList.contains('active-view')) load(true);
    else { ++requestVersion; lastKey = null; }
  });
  observer.observe(view, {attributes:true,attributeFilter:['class']});
})();
