/* Delayed aggregate review; no polling, gameplay hooks or live analysis. */
(() => {
  'use strict';
  const view = document.getElementById('mdaView');
  if (!view) return;
  const el = id => document.getElementById(id);
  const metrics = {
    rfi: ['RFI', '誰も参加していない状況でのオープン'],
    three_bet: ['3ベット', '最初のレイズに対するリレイズ'],
    fold_to_three_bet: ['3ベットにフォールド', 'オープンした人の直接の応答'],
    flop_cbet: ['フロップCB', 'プリフロップの最終レイザーによる最初のベット'],
    fold_to_flop_cbet: ['フロップCBにフォールド', 'CBに直接応答する機会']
  };
  const labels = {
    unraised:'レイズなし', srp:'シングルレイズ', '3bet':'3ベット', '4bet_plus':'4ベット以上',
    under_20bb:'20bb未満', '20_to_39bb':'20–40bb未満',
    '40_to_99bb':'40–100bb未満', '100bb_plus':'100bb以上'
  };
  let data = null, version = 0, controller = null;
  const node = (tag, text, cls) => {
    const n = document.createElement(tag);
    if (text !== undefined) n.textContent = text;
    if (cls) n.className = cls;
    return n;
  };
  function label(key) {
    if (labels[key]) return labels[key];
    const match = /^(unpaired|paired|trips_plus|double_paired):([1-5])max$/.exec(key);
    if (!match) return key;
    return ({unpaired:'ペアなし',paired:'ペアあり',trips_plus:'トリップス以上',double_paired:'2ペア'})[match[1]] +
      '・同スート最大' + match[2] + '枚';
  }
  function cellRow(title, cell) {
    const row = node('div', undefined, 'mda-stat');
    row.append(node('strong', title));
    if (!cell || cell.status !== 'observed') {
      row.append(node('span', 'サンプル不足', 'mda-muted'));
      return row;
    }
    const interval = cell.wilson_95_percent;
    row.append(node('span', cell.percentage.toLocaleString('ja-JP') + '%', 'mda-rate'));
    row.append(node('span', cell.chosen.toLocaleString('ja-JP') + ' / ' +
      cell.opportunities.toLocaleString('ja-JP') + '機会', 'mda-count'));
    row.append(node('span', '95%参考区間 ' + interval[0] + '–' + interval[1] + '%', 'mda-muted'));
    return row;
  }
  function render() {
    el('mdaMetrics').replaceChildren();
    if (!data) return;
    const group = data.cohorts_by_players_dealt_in[el('mdaSize').value];
    const stamp = s => new Date(s).toLocaleString('ja-JP', {timeZone:'Asia/Tokyo'});
    el('mdaMessage').textContent = '集計対象の期限：' + stamp(data.data_as_of) +
      ' ／ 作成：' + stamp(data.generated_at) + '（日本時間）' +
      (group ? ' ／ 完了ハンド ' + group.completed_hands_used.toLocaleString('ja-JP') + '件' : ' ／ この人数のデータはありません。');
    if (!group) return;
    const dimension = el('mdaDimension').value;
    for (const [key, [title, definition]] of Object.entries(metrics)) {
      const card = node('section', undefined, 'mda-metric card');
      card.append(node('h4', title), node('p', definition, 'hint'));
      const metric = group.metrics[key];
      if (!dimension) card.append(cellRow('全体', metric));
      else {
        const cells = (metric.cuts || {})[dimension] || {};
        if (!Object.keys(cells).length) card.append(node('p', '対象データなし', 'mda-muted'));
        for (const [name, cell] of Object.entries(cells)) card.append(cellRow(label(name), cell));
      }
      el('mdaMetrics').append(card);
    }
  }
  async function load() {
    if (!view.classList.contains('active-view')) return;
    if (controller) controller.abort();
    controller = new AbortController();
    const request = ++version;
    data = null;
    el('mdaMetrics').replaceChildren();
    el('mdaMessage').textContent = '集計データを読み込んでいます。';
    try {
      const res = await fetch('/api/admin/mda/population', {
        credentials:'same-origin', cache:'no-store', signal:controller.signal,
        headers:{Accept:'application/json'}
      });
      if (request !== version) return;
      if (res.status === 401 || res.status === 403) {
        el('mdaMessage').textContent = '管理者としてのログインが必要です。'; return;
      }
      if (!res.ok) throw new Error('response');
      const doc = await res.json();
      if (request !== version || !view.classList.contains('active-view')) return;
      if (doc.status === 'not_ready') {
        el('mdaMessage').textContent = doc.message || '集計データは準備中です。'; return;
      }
      if (doc.status !== 'ok' || doc.format_version !== 'mda-population-v2-review' ||
          doc.game !== 'Ring' || !doc.no_hand_class_inference) throw new Error('format');
      data = doc;
      render();
    } catch (err) {
      if (request === version && err.name !== 'AbortError') {
        data = null;
        el('mdaMetrics').replaceChildren();
        el('mdaMessage').textContent = '集計データを取得できません。更新状態や接続を確認してください。';
      }
    }
  }
  el('mdaSize').addEventListener('change', render);
  el('mdaDimension').addEventListener('change', render);
  el('mdaRefresh').addEventListener('click', load);
  let active = view.classList.contains('active-view');
  new MutationObserver(() => {
    const next = view.classList.contains('active-view');
    if (next === active) return;
    active = next;
    if (next) load();
    else { ++version; if (controller) controller.abort(); data = null; el('mdaMetrics').replaceChildren(); }
  }).observe(view, {attributes:true, attributeFilter:['class']});
  if (active) load();
})();
