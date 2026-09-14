const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const nodes = new Map();
const context = {
  Intl, Date, setTimeout, setInterval: () => {},
  document: {addEventListener() {}, querySelector(selector) {
    if (!nodes.has(selector)) nodes.set(selector, {innerHTML: '', textContent: ''});
    return nodes.get(selector);
  }},
};
vm.createContext(context);
vm.runInContext(fs.readFileSync('admin_static/ops_dashboard.js', 'utf8').replace(
  '  async function loadAll()', '  globalThis.renderForTest=renderOps;\n  async function loadAll()'), context);
function render(p95, waiting=0, errors=0, samples=5) {
  context.renderForTest({}, {errors_24h: errors, recent_errors: [], runtime: {
    api_latency: {p95_ms:p95, samples}, db_pool:{backend:'postgres', active:true, requests_waiting:waiting},
    websocket:{connections:0},
  }});
  return nodes.get('#opsHealth').innerHTML;
}
function card(html, title) {return html.split('</div>').find(s=>s.includes(title));}
for (const [p95, expected] of [[500,'ok'],[500.01,'warning'],[1000,'warning'],[1000.01,'critical'],[null,'unknown']]) {
  assert.match(card(render(p95), 'API latency'), new RegExp(`ops-state-${expected}`));
}
assert.match(card(render(0,0,0,0), 'API latency'), /ops-state-unknown/);
assert.match(card(render(10,1), 'DB pool'), /ops-state-warning/);
assert.match(card(render(10,0), 'DB pool'), /ops-state-ok/);
assert.match(card(render(10,0,1), '24時間エラー'), /ops-state-warning/);
assert.match(card(render(10), 'WebSocket'), /ops-state-info/);
context.renderForTest({}, {});
assert.match(card(nodes.get('#opsHealth').innerHTML, 'API latency'), /未計測/);
assert.match(card(nodes.get('#opsHealth').innerHTML, 'API latency'), /P95 —/);
assert.match(card(nodes.get('#opsHealth').innerHTML, '24時間エラー'), /未計測/);
console.log('JJ_OPS_ALERTS_OK');
