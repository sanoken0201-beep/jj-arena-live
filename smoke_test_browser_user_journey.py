from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "materialized_v1244" / "static"

STUB = r'''
<script>
(() => {
  let loggedIn = false;
  const user = {id:101,name:'ユーザーテスト',role:'member',xp:0,disabled:0,ranking_name:'ユーザーテスト',created_at:'2026-09-11T00:00:00Z'};
  const rankings = [{name:'ユーザーテスト',points:10,club_points:10,online_points:0,games:1,online_hands:0,best:10,wins:1,rank:1,season:'fall'}];
  const tables = [
    {id:'jj-table-a',name:'JJ Table A',status:'waiting',players:0,seated:0,sitouts:0,busted:0,max_seats:6,small_blind:50,big_blind:100,starting_stack:15000,starting_stack_bb:150,rake_percent:0.1,rake_cap_bb:5},
    {id:'jj-table-b',name:'JJ Table B',status:'waiting',players:0,seated:0,sitouts:0,busted:0,max_seats:6,small_blind:50,big_blind:100,starting_stack:15000,starting_stack_bb:150,rake_percent:0.1,rake_cap_bb:5},
  ];
  const progress = {answered:0,correct:0,earned:0,remaining:10,total:10,max_daily_reward:100,carried_answers:0};
  const quizQuestion = {
    id:'dqa-browser-fixture-0001', date:'2026-09-11', slot:1,
    category:'pot_odds', category_label:'POT ODDS',
    prompt:'Pot 100 に 50 のベット。コールに必要な最低勝率は？',
    choices:[
      {value:'choice-a',label:'20%'},
      {value:'choice-b',label:'25%'},
      {value:'choice-c',label:'33%'},
      {value:'choice-d',label:'40%'},
    ],
    glossary:[], reward:10, progress, done:false,
  };
  const homeOverview = {
    quiz: progress,
    points:{season_total:10,rank:1,month_total:10,month_rank:1},
    performance:{net_bb_30d:0,hands_30d:0,bb_per_100:null},
    learning:{title:'今日のクイズ',fact:'まず1問解いて感覚を整えましょう。'},
    recent_hands:[], articles:[],
  };
  window.__jjMissingRequests = [];
  window.__jjRequests = [];
  function jsonResponse(body, status=200){
    return new Response(JSON.stringify(body), {status, headers:{'Content-Type':'application/json'}});
  }
  window.fetch = async (input, options={}) => {
    const raw = typeof input === 'string' ? input : input.url;
    const url = new URL(raw, 'https://fixture.invalid');
    const path = url.pathname;
    const method = String(options.method || 'GET').toUpperCase();
    window.__jjRequests.push(`${method} ${path}`);
    if(path === '/api/me') return loggedIn ? jsonResponse(user) : jsonResponse({detail:'authentication required'}, 401);
    if(path === '/api/auth/pin' && method === 'POST') { loggedIn = true; return jsonResponse({user,created:true}); }
    if(path === '/api/auth/logout' && method === 'POST') { loggedIn = false; return jsonResponse({ok:true}); }
    if(path === '/api/rankings') return jsonResponse(rankings);
    if(path === '/api/schedules') return jsonResponse([]);
    if(path === '/api/announcements') return jsonResponse([]);
    if(path === '/api/tables') return jsonResponse(tables);
    if(path === '/api/online/results') return jsonResponse([]);
    if(path === '/api/online/summary') return jsonResponse({hands:0,voided_hands:0,rake_bb:0,gross_pot_bb:0});
    if(path === '/api/threads') return jsonResponse([]);
    if(path === '/api/learning-content') return loggedIn ? jsonResponse({articles:[],videos:[],policy:{articles:'ja-only'}}) : jsonResponse({detail:'authentication required'},401);
    if(path === '/api/home/overview') return jsonResponse(homeOverview);
    if(path === '/api/quiz/question') return jsonResponse(quizQuestion);
    window.__jjMissingRequests.push(`${method} ${path}`);
    return jsonResponse({detail:`missing fixture for ${method} ${path}`}, 500);
  };
})();
</script>
'''

DRIVER = r'''
<script>
(async () => {
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  async function waitFor(fn, label){
    for(let i=0;i<160;i++){
      try{ if(fn()) return; }catch{}
      await sleep(25);
    }
    throw new Error(`timeout: ${label}`);
  }
  const checks = {};
  try{
    await waitFor(() => !document.getElementById('authView').classList.contains('hidden'), 'auth visible');
    checks.firstVisitLogin = document.getElementById('appView').classList.contains('hidden');

    document.getElementById('loginName').value = 'ユーザーテスト';
    document.getElementById('loginPin').value = '123456';
    document.getElementById('pinForm').requestSubmit();
    await waitFor(() => !document.getElementById('appView').classList.contains('hidden') && document.getElementById('userName').textContent === 'ユーザーテスト', 'login');
    checks.login = true;
    checks.memberAdminHidden = [...document.querySelectorAll('.admin-only')].every(el => el.classList.contains('hidden'));
    await waitFor(() => document.getElementById('homeTop').textContent.includes('ユーザーテスト') && document.getElementById('homeTables').textContent.includes('JJ Table A'), 'home data');
    checks.homeLoaded = true;

    document.querySelector('.nav[data-view="ranking"]').click();
    await waitFor(() => document.getElementById('rankingView').classList.contains('active-view') && document.getElementById('rankBody').textContent.includes('ユーザーテスト'), 'ranking');
    checks.rankingNavigation = true;

    document.querySelector('.nav[data-view="tables"]').click();
    await waitFor(() => document.getElementById('tablesView').classList.contains('active-view') && document.querySelectorAll('#tableCards [data-open-table]').length === 2, 'tables');
    checks.tableLobbyNavigation = document.getElementById('tableCards').textContent.includes('OPEN TABLE');

    document.querySelector('.nav[data-view="lab"]').click();
    await waitFor(() => document.getElementById('labView').classList.contains('active-view') && document.querySelectorAll('#quizChoices button').length >= 4, 'poker lab');
    checks.learningNavigation = document.getElementById('quizStage').textContent.includes('POT ODDS') || document.getElementById('quizStage').textContent.includes('最低勝率');

    document.querySelector('.nav[data-view="home"]').click();
    await waitFor(() => document.getElementById('homeView').classList.contains('active-view'), 'home return');
    checks.returnHome = true;
    checks.noHorizontalOverflow = document.documentElement.scrollWidth <= innerWidth + 2;

    document.getElementById('headerLogoutBtn').click();
    await waitFor(() => !document.getElementById('authView').classList.contains('hidden') && document.getElementById('appView').classList.contains('hidden'), 'logout');
    checks.logout = true;
    checks.noMissingRequests = window.__jjMissingRequests.length === 0;
  }catch(error){
    checks.driverError = String(error && error.stack || error);
  }
  const ok = Object.values(checks).every(v => v === true);
  const pre = document.createElement('pre');
  pre.id = 'userJourneyResult';
  pre.dataset.userJourneyOk = ok ? '1' : '0';
  pre.textContent = JSON.stringify({checks,missing:window.__jjMissingRequests,requests:window.__jjRequests});
  document.body.appendChild(pre);
})();
</script>
'''


def chrome_binary() -> str:
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        path = shutil.which(name)
        if path:
            return path
    raise AssertionError("Chrome/Chromium is required for browser user-journey regression")


def fixture_html() -> str:
    text = (STATIC / "index.html").read_text(encoding="utf-8")
    text = text.replace('/static/styles.css?v=56', 'styles.css')
    text = text.replace('/static/app.js?v=56', 'app.js')
    marker = '<script src="app.js"></script>'
    assert marker in text, "materialized index no longer exposes the expected app.js script"
    return text.replace(marker, STUB + marker + DRIVER)


def run_browser(chrome: str, fixture: Path, width: int, height: int) -> str:
    url = fixture.resolve().as_uri()
    last = ""
    for _ in range(2):
        proc = subprocess.run(
            [
                chrome,
                "--headless",
                "--no-sandbox",
                "--disable-gpu",
                "--allow-file-access-from-files",
                "--run-all-compositor-stages-before-draw",
                "--virtual-time-budget=6000",
                f"--window-size={width},{height}",
                "--dump-dom",
                url,
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=40,
        )
        last = proc.stdout
        if 'data-user-journey-ok=' in last:
            return last
    return last


def main() -> None:
    chrome = chrome_binary()
    with tempfile.TemporaryDirectory(prefix="jj-browser-journey-") as td:
        work = Path(td)
        shutil.copy2(STATIC / "app.js", work / "app.js")
        shutil.copy2(STATIC / "styles.css", work / "styles.css")
        fixture = work / "index.html"
        fixture.write_text(fixture_html(), encoding="utf-8")

        desktop = run_browser(chrome, fixture, 1440, 900)
        mobile = run_browser(chrome, fixture, 390, 844)
        assert 'data-user-journey-ok="1"' in desktop, desktop[-4500:]
        assert 'data-user-journey-ok="1"' in mobile, mobile[-4500:]

    print("JJ_BROWSER_USER_JOURNEY_OK desktop=1 mobile=1")


if __name__ == "__main__":
    main()
