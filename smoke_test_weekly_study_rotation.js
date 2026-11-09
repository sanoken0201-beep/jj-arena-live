'use strict';

// Verify the actual compiled browser asset without evaluating unrelated SPA
// transforms that wrap renderHome in the modern production bundle.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const path = process.argv[2];
assert.ok(path, 'Pass the compiled static/app.js path');
const source = fs.readFileSync(path, 'utf8').replace(/\r\n/g, '\n');
new vm.Script(source, {filename: path});
assert.ok(source.includes('JJ_WEEKLY_GTO_ROTATION_V1'));
assert.ok(source.includes('renderWeeklyStudy(data.articles||[]);'), 'API articles must refresh weekly cards');
assert.ok(source.includes("document.addEventListener('visibilitychange'"), 'Visible tabs must refresh');
assert.ok(source.includes('scheduleWeeklyRotation();'), 'Open tabs must roll over after Monday midnight');

const begin = source.indexOf('// Japanese article fallbacks are embedded');
const boot = "if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',renderWeeklyStudy,{once:true});else renderWeeklyStudy();";
const end = source.indexOf(boot, begin);
assert.ok(begin >= 0 && end > begin);
const snippet = source.slice(begin, end + boot.length);
const FIXED_NOW = Date.parse('2026-11-09T12:00:00+09:00');

function harness(readyState) {
  const nodes = new Map(), events = new Map();
  class Element {
    constructor() { this.dataset = {}; this.children = []; this._html = ''; this._grid = null; }
    set id(value) { this._id = value; nodes.set(value, this); }
    get id() { return this._id; }
    set innerHTML(value) { this._html = value; }
    get innerHTML() { return this._html; }
    appendChild(child) { this.children.push(child); return child; }
    get firstElementChild() { return null; }
    querySelector(selector) {
      if (selector !== '.study-grid') return null;
      if (!this._grid) this._grid = new Element();
      return this._grid;
    }
  }
  for (const id of ['homeView', 'labView']) {
    const element = new Element();
    element.id = id;
  }
  const document = {
    readyState,
    createElement: () => new Element(),
    addEventListener: (name, fn) => events.set(name, fn),
  };
  class FixedDate extends Date { static now() { return FIXED_NOW; } }
  const ctx = vm.createContext({
    Date: FixedDate, URL, document,
    $: selector => nodes.get(selector.slice(1)) || null,
    safe: value => String(value ?? '').replace(/[&<>"']/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c])),
  });
  vm.runInContext(snippet + '\nglobalThis.weekly={studyWeekSeed,studyIndex,renderWeeklyStudy,jjJapaneseStudyArticles,jjJapaneseArticleFallback};', ctx);
  if (readyState === 'loading') events.get('DOMContentLoaded')();
  return {nodes, api: ctx.weekly};
}

for (const readyState of ['complete', 'loading']) {
  const {nodes, api} = harness(readyState);
  const monday = Date.parse('2026-11-09T00:00:00+09:00');
  assert.equal(api.studyWeekSeed(monday) - api.studyWeekSeed(monday - 1), 1);
  assert.equal(api.studyWeekSeed(monday + 6 * 86400000), api.studyWeekSeed(monday));
  assert.equal(api.studyWeekSeed(monday + 7 * 86400000), api.studyWeekSeed(monday) + 1);

  const fallback = api.jjJapaneseArticleFallback;
  assert.ok(fallback.length >= 4);
  const pair = time => {
    const index = api.studyIndex(fallback.length, time);
    return [fallback[index].url, fallback[(index + 1) % fallback.length].url];
  };
  const current = pair(monday), next = pair(monday + 7 * 86400000);
  assert.ok(current.every(url => !next.includes(url)), 'Adjacent-week fallback pairs overlap');

  const dynamic = Array.from({length: 8}, (_, i) => ({
    title: 'ポーカーのレンジ戦略を学ぶ第' + (i + 1) + '回',
    language: 'ja',
    url: 'https://japan.gtowizard.com/blog/weekly-test-' + (i + 1) + '/',
    summary: '日本語で学ぶポーカー戦略の解説記事です。',
    source: 'untrusted source',
  }));
  const invalid = {
    title: 'English only strategy', language: 'en',
    url: 'https://blog.gtowizard.com/invalid/',
    summary: 'Not a Japanese article',
  };

  api.renderWeeklyStudy([invalid, ...dynamic]);
  const pool = api.jjJapaneseStudyArticles([...dynamic, ...fallback]);
  const index = api.studyIndex(pool.length);
  const expected = [pool[index], pool[(index + 1) % pool.length]];
  assert.ok(expected.every(item => item.url.includes('/weekly-test-')), 'Weekly cards must select fresh RSS candidates');
  const home = nodes.get('weeklyStudyHome'), lab = nodes.get('weeklyStudyLab');
  assert.ok(home && lab);
  const homeGrid = home.querySelector('.study-grid');
  const labGrid = lab.querySelector('.study-grid');
  for (const article of expected) {
    assert.ok(homeGrid.innerHTML.includes(article.url), 'Dynamic article missing from home cards');
    assert.ok(labGrid.innerHTML.includes(article.url), 'Dynamic article missing from Poker Lab');
  }
  assert.ok(!homeGrid.innerHTML.includes('blog.gtowizard.com'), 'Non-Japanese article escaped filter');
  api.renderWeeklyStudy([]);
  assert.equal(nodes.get('homeView').children.length, 1, 'Home weekly section duplicated');
  assert.equal(nodes.get('labView').children.length, 1, 'Lab weekly section duplicated');
  const fallbackGrid = home.querySelector('.study-grid').innerHTML;
  const selectedFallback = pair(FIXED_NOW);
  for (const url of selectedFallback) assert.ok(fallbackGrid.includes(url), 'Offline fallback was not restored');
}

console.log('JJ_WEEKLY_GTO_ROTATION_OK');
