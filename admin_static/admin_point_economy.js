/* Admin-only point history and inflation analysis. Loaded on the separate /admin console. */
(() => {
  'use strict';
  const $ = selector => document.querySelector(selector);
  const labels = {club:'入力', online:'オンライン卓', quiz:'今日の問題', other:'その他・補正'};
  const fmt = value => Number(value || 0).toLocaleString('ja-JP', {maximumFractionDigits:2});
  const signed = value => `${Number(value) >= 0 ? '+' : ''}${fmt(value)}`;
  const safe = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[char]));
  const state = {loaded:false, seasonsLoaded:false, request:0, offset:0, next:null};

  async function get(path) {
    const response = await fetch('/api' + path, {credentials:'same-origin'});
    let data;
    try { data = await response.json(); } catch { data = null; }
    if (!response.ok) throw new Error(typeof data?.detail === 'string' ? data.detail : `HTTP ${response.status}`);
    return data;
  }

  function chart(rows) {
    if (!rows.length) return '<div class="empty-state">推移データはありません</div>';
    const width = 720, height = 224, left = 61, right = 18, top = 14, bottom = 31;
    const values = rows.flatMap(r => [Number(r.cumulative), Number(r.quiz_cumulative)]);
    const low = Math.min(0, ...values), high = Math.max(0, ...values), range = high - low || 1;
    const x = i => left + (width - left - right) * (rows.length === 1 ? .5 : i / (rows.length - 1));
    const y = value => top + (height - top - bottom) * (high - Number(value)) / range;
    const points = key => rows.map((r, i) => `${x(i).toFixed(2)},${y(r[key]).toFixed(2)}`).join(' ');
    const grid = [0, .5, 1].map(t => {
      const yy = top + t * (height - top - bottom);
      return `<line x1="${left}" y1="${yy}" x2="${width-right}" y2="${yy}" stroke="#e1e9e3"/><text x="${left-8}" y="${yy+4}" text-anchor="end" font-size="11" fill="#67776b">${safe(fmt(high-range*t))}</text>`;
    }).join('');
    return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="累積ポイント総量の推移。${safe(rows[0].date)}から${safe(rows[rows.length-1].date)}"><title>ポイント総量の推移</title>${grid}<polyline points="${points('cumulative')}" fill="none" stroke="#126d4a" stroke-width="3" stroke-linejoin="round"/><polyline points="${points('quiz_cumulative')}" fill="none" stroke="#d67c59" stroke-width="2.5" stroke-linejoin="round"/><text x="${left}" y="${height-8}" font-size="11" fill="#67776b">${safe(rows[0].date)}</text><text x="${width-right}" y="${height-8}" text-anchor="end" font-size="11" fill="#67776b">${safe(rows[rows.length-1].date)}</text></svg>`;
  }

  function render(data, offset) {
    const total = data.totals || {};
    const previous = Number(total.total || 0) - Number(data.last_7_days || 0);
    const inflationRate = previous > 0 ? `（${signed((Number(data.last_7_days) / previous * 100).toFixed(1))}%）` : '（基準総量が0以下のため率は算出しません）';
    const numbers = [
      ['現在の累積総量', `${fmt(total.total)} pt`],
      ['直近7日間の純増減', `${signed(data.last_7_days)} pt`, inflationRate],
      ['直近30日間の純増減', `${signed(data.last_30_days)} pt`],
      ['今日の問題の累積', `${signed(total.quiz)} pt`],
    ];
    $('#economyNumbers').innerHTML = numbers.map(([label, value, sub]) => `<div class="economy-kpi"><span>${safe(label)}</span><strong>${safe(value)}</strong>${sub ? `<small>${safe(sub)}</small>` : ''}</div>`).join('');
    $('#economyChart').innerHTML = chart(data.daily || []);

    const days = (data.daily || []).filter(r => r.change || r.club || r.online || r.quiz || r.other).reverse();
    $('#economyDaily').innerHTML = days.map(r => `<tr><td>${safe(r.date)}</td><td>${signed(r.club)}</td><td>${signed(r.online)}</td><td>${signed(r.quiz)}</td><td>${signed(r.other)}</td><td><b>${signed(r.change)}</b></td><td>${fmt(r.cumulative)}</td></tr>`).join('') || '<tr><td colspan="7">まだ記録がありません</td></tr>';

    const history = data.history || [];
    $('#economyHistory').innerHTML = history.map(r => `<div class="economy-event"><div class="economy-event-top"><span><span class="economy-source">${safe(labels[r.source] || r.source)}</span><b>${safe(r.player)}</b></span><strong class="${Number(r.points) >= 0 ? 'economy-plus' : 'economy-minus'}">${signed(r.points)}</strong></div><div class="economy-event-detail">${safe(r.date)} · ${safe(r.detail)}</div></div>`).join('') || '<div class="empty-state">該当する履歴はありません</div>';
    state.offset = offset;
    state.next = data.next_offset;
    $('#economyPrevious').disabled = offset === 0;
    $('#economyNext').disabled = data.next_offset == null;
    $('#economyPageLabel').textContent = history.length ? `${offset+1}〜${offset+history.length}件目` : '0件';
    $('#economyFootnote').textContent = `入力 ${signed(total.club)} pt / オンライン ${signed(total.online)} pt / 今日の問題 ${signed(total.quiz)} pt / その他 ${signed(total.other)} pt。${data.definition || ''} 日別集計は日本時間で行います。種類の選択は取引履歴のみ絞り込み、総量・グラフは全種類を表示します。`;
  }

  async function load(offset = 0) {
    if (!$('#economyView')?.classList.contains('active')) return;
    const request = ++state.request;
    $('#economyStatus').textContent = 'ポイント履歴を集計中…';
    const query = new URLSearchParams({season:$('#economySeason').value, source:$('#economySource').value, offset:String(offset), limit:'50'});
    try {
      const data = await get('/admin/point-economy?' + query.toString());
      if (request !== state.request || !$('#economyView').classList.contains('active')) return;
      render(data, offset);
      state.loaded = true;
      $('#economyStatus').textContent = `集計完了 · ${data.as_of}（日本時間）`;
    } catch (error) {
      if (request === state.request) $('#economyStatus').textContent = '読み込みできません: ' + error.message;
    }
  }

  async function initializeSeasons() {
    if (state.seasonsLoaded) return;
    const rows = await get('/seasons');
    const active = rows.find(r => r.status === 'active');
    const options = [
      ...(active ? [{value:active.season_id, name:active.name + '（現在）'}] : [{value:'fall', name:'現在のシーズン'}]),
      ...rows.filter(r => r.status === 'archived').map(r => ({value:r.season_id, name:r.name})),
    ];
    const selected = $('#economySeason').value;
    $('#economySeason').innerHTML = options.map(r => `<option value="${safe(r.value)}">${safe(r.name)}</option>`).join('');
    if (options.some(r => r.value === selected)) $('#economySeason').value = selected;
    state.seasonsLoaded = true;
  }

  window.jjLoadPointEconomy = async () => {
    if (!$('#economyView')?.classList.contains('active')) return;
    if (state.loaded) return;
    try { await initializeSeasons(); } catch (error) {
      $('#economyStatus').textContent = 'シーズンの取得に失敗しました: ' + error.message;
      return;
    }
    await load(0);
  };
  $('#economySeason').addEventListener('change', () => load(0));
  $('#economySource').addEventListener('change', () => load(0));
  $('#economyRefresh').addEventListener('click', () => load(state.offset));
  $('#economyPrevious').addEventListener('click', () => load(Math.max(0, state.offset - 50)));
  $('#economyNext').addEventListener('click', () => { if (state.next != null) load(state.next); });
})();
