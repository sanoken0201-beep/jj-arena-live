'use strict';

// Run against the reconstructed production JavaScript, not a copied UI fixture:
// node smoke_test_learning_ui.js /path/to/runtime/static/app.js
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const runtimePath = process.argv[2];
assert.ok(runtimePath, 'Pass the reconstructed runtime static/app.js path');
const source = fs.readFileSync(runtimePath, 'utf8').replace(/\r\n/g, '\n');
new vm.Script(source, {filename: runtimePath});
assert.ok(!source.includes('https://blog.gtowizard.com/'), 'English article library must be absent from production JS');

function extract(start, end) {
  const from = source.indexOf(start);
  const through = source.indexOf(end, from);
  assert.ok(from >= 0 && through >= from, `Missing production fragment: ${start}`);
  return source.slice(from, through + end.length);
}

const weeklySource = extract(
  '// Japanese article fallbacks are embedded',
  "if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',renderWeeklyStudy,{once:true});else renderWeeklyStudy();"
);
const learningSource = extract(
  '// v1.19.2 Japanese-first learning share.',
  '    return result;\n  };'
);

function harness(readyState) {
  const nodes = new Map();
  const events = new Map();
  class Element {
    constructor() { this.dataset = {}; this.children = []; this._html = ''; }
    set id(value) { this._id = value; nodes.set(value, this); }
    get id() { return this._id; }
    set innerHTML(value) {
      this._html = value;
      for (const match of value.matchAll(/\bid="([^"]+)"/g)) {
        const child = new Element();
        child.id = match[1];
      }
    }
    get innerHTML() { return this._html; }
    appendChild(node) { this.children.push(node); return node; }
    querySelector() { return null; }
    get firstElementChild() { return null; }
  }
  for (const id of ['homeView', 'labView']) {
    const node = new Element();
    node.id = id;
  }
  const state = {apiCalls: 0, homeCalls: 0, apiResult: null, fail: false};
  const context = vm.createContext({
    URL, Intl,
    document: {
      readyState,
      createElement: () => new Element(),
      addEventListener: (name, fn) => events.set(name, fn),
    },
    $: selector => nodes.get(selector.slice(1)) || null,
    safe: value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[ch])),
    api: async path => {
      assert.equal(path, '/learning-content');
      state.apiCalls += 1;
      if (state.fail) throw new Error('feed endpoint unavailable');
      return state.apiResult;
    },
    renderHome: async () => { state.homeCalls += 1; return 23; },
  });
  vm.runInContext(weeklySource + '\n' + learningSource + '\nglobalThis.ui = {renderWeeklyStudy, jjV192LearningShell, jjV192RenderArticles, jjV192RenderLearning, jjJapaneseStudyArticles, renderHome, fallback: jjJapaneseArticleFallback};', context);
  if (readyState === 'loading') events.get('DOMContentLoaded')();
  return {nodes, state, ui: context.ui};
}

function assertJapaneseLinks(node, minimum = 1) {
  assert.ok(node, 'Expected article section');
  const links = [...node.innerHTML.matchAll(/href="([^"]+)"/g)];
  assert.ok(links.length >= minimum, 'Japanese fallback articles should remain visible');
  for (const [, href] of links) {
    const url = new URL(href);
    assert.equal(url.protocol, 'https:');
    assert.equal(url.hostname, 'japan.gtowizard.com');
    assert.ok(url.pathname.startsWith('/blog/'));
    assert.equal(url.search, '');
  }
}

(async () => {
  for (const readyState of ['complete', 'loading']) {
    const {nodes, state, ui} = harness(readyState);
    assert.ok(ui.fallback.length >= 2);
    assertJapaneseLinks(nodes.get('weeklyStudyHome'), 2);
    assertJapaneseLinks(nodes.get('weeklyStudyLab'), 3);
    assert.ok(!nodes.get('weeklyStudyHome').innerHTML.includes('CashとMTTを1本ずつ'));
    assert.ok(!nodes.get('weeklyStudyHome').innerHTML.includes(' min'));
    ui.renderWeeklyStudy();
    assert.equal(nodes.get('homeView').children.length, 1, 'Repeated render must not duplicate weekly cards');
    ui.jjV192LearningShell();
    assertJapaneseLinks(nodes.get('jjLearningArticles'), 2);

    const valid = {title: 'ポーカーの学習方法を考える', language: 'ja', url: 'https://japan.gtowizard.com/blog/ja-test/', summary: 'レンジを理解して戦略を学びます。', source: 'untrusted source label'};
    const invalid = [
      {...valid, language: 'en', title: '英語の指定がある記事'},
      {...valid, title: 'Playing Under Ten Big Blinds'},
      {...valid, title: 'A very long English poker article title あ'},
      {...valid, title: 'A poker article ー'},
      {...valid, title: '撲克策略研究'},
      {...valid, url: 'https://blog.gtowizard.com/ja-test/'},
      {...valid, url: 'https://japan.gtowizard.com.evil.test/blog/ja-test/'},
      {...valid, url: 'http://japan.gtowizard.com/blog/ja-test/'},
      {...valid, url: 'https://user@japan.gtowizard.com/blog/ja-test/'},
      {...valid, url: 'https://japan.gtowizard.com:8443/blog/ja-test/'},
      {...valid, url: 'https://japan.gtowizard.com/blog/ja-test/?lang=en'},
      {...valid, url: 'https://japan.gtowizard.com/blog/videos/test/'},
      {...valid, url: 'javascript:alert(1)'},
      null,
    ];
    assert.equal(ui.jjJapaneseStudyArticles(invalid).length, 0);
    state.apiResult = {articles: [...invalid, valid, {...valid}], videos: []};
    await ui.jjV192RenderLearning();
    const articles = nodes.get('jjLearningArticles');
    assertJapaneseLinks(articles);
    assert.equal([...articles.innerHTML.matchAll(/class="jj-study-card"/g)].length, 1, 'Only accepted, deduplicated article is rendered');
    assert.ok(articles.innerHTML.includes(valid.title));
    assert.ok(!articles.innerHTML.includes('untrusted source label'));
    assert.ok(!articles.innerHTML.includes('English'));

    state.apiResult = {articles: invalid, videos: []};
    await ui.jjV192RenderLearning();
    assertJapaneseLinks(articles, 2);
    assert.ok(!articles.innerHTML.includes(valid.title));
    state.fail = true;
    await ui.jjV192RenderLearning();
    assertJapaneseLinks(articles, 2);
    assert.ok(nodes.get('jjLearningVideos').innerHTML.includes('動画を取得できませんでした'));
    ui.jjV192RenderArticles(null);
    assertJapaneseLinks(articles, 2);
    ui.jjV192RenderArticles([{...valid, summary: 'This is an English summary.'}]);
    assert.ok(!articles.innerHTML.includes('English summary'));
    assert.equal(await ui.renderHome(), 23, 'Original home data loading remains intact');
    assert.equal(state.homeCalls, 1);
    await Promise.resolve();
    assertJapaneseLinks(articles, 2);
  }
  console.log('JJ_LEARNING_UI_SMOKE_OK');
})().catch(error => { console.error(error); process.exitCode = 1; });
