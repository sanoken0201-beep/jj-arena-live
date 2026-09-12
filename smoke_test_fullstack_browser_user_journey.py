from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from contextlib import asynccontextmanager
from pathlib import Path


ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "materialized_v1244" / "static"

DRIVER = r'''
<script>
(async () => {
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  async function waitFor(fn, label, loops=240){
    for(let i=0;i<loops;i++){
      try{ if(fn()) return; }catch{}
      await sleep(25);
    }
    throw new Error(`timeout: ${label}`);
  }
  async function go(view){
    const mobile = innerWidth <= 700;
    if(mobile && ['home','ranking','tables'].includes(view)){
      await waitFor(() => document.querySelector(`[data-mobile-view="${view}"]`), `mobile ${view} button`);
      document.querySelector(`[data-mobile-view="${view}"]`).click();
    }else if(mobile){
      document.querySelector('[data-mobile-more]').click();
      await waitFor(() => !document.getElementById('mobileMore').classList.contains('hidden'), 'mobile more');
      await waitFor(() => document.querySelector(`[data-more-view="${view}"]`), `more ${view}`);
      document.querySelector(`[data-more-view="${view}"]`).click();
    }else{
      document.querySelector(`.sidebar .nav[data-view="${view}"]`).click();
    }
    await waitFor(() => document.getElementById(`${view}View`)?.classList.contains('active-view'), `${view} view`);
  }
  const checks = {};
  try{
    await waitFor(() => !document.getElementById('authView').classList.contains('hidden'), 'login screen');
    checks.firstVisitLogin = document.getElementById('appView').classList.contains('hidden');

    document.getElementById('loginName').value = 'ブラウザユーザー';
    document.getElementById('loginPin').value = '123456';
    document.getElementById('pinForm').requestSubmit();
    await waitFor(() => !document.getElementById('appView').classList.contains('hidden') && document.getElementById('userName').textContent === 'ブラウザユーザー', 'real login');
    checks.realLogin = true;
    checks.memberAdminHidden = [...document.querySelectorAll('.admin-only')].every(el => el.classList.contains('hidden'));
    await waitFor(() => document.getElementById('homeTables').textContent.includes('JJ Table A'), 'home tables');
    await waitFor(() => document.getElementById('jjHomeHubGrid')?.textContent.includes('今日のクイズ') === true, 'home overview');
    checks.home = true;

    await go('lab');
    await waitFor(() => document.querySelectorAll('#quizChoices [data-daily-answer]').length >= 4, 'daily quiz choices');
    const firstChoice = document.querySelector('#quizChoices [data-daily-answer]');
    firstChoice.click();
    await waitFor(() => document.getElementById('quizStage').textContent.includes('この問題') && document.getElementById('quizScore').textContent.includes('+10pt'), 'quiz reward');
    checks.quizAward = document.getElementById('quizStage').textContent.includes('+10pt');

    await go('ranking');
    await waitFor(() => document.getElementById('rankBody').textContent.includes('ブラウザユーザー'), 'ranking row');
    checks.rankingAfterQuiz = document.getElementById('rankBody').textContent.includes('10');

    await go('discussion');
    document.getElementById('newThreadBtn').click();
    await waitFor(() => document.getElementById('threadForm'), 'thread modal');
    document.querySelector('#threadForm [name="title"]').value = 'ブラウザからの戦略相談';
    document.querySelector('#threadForm [name="body"]').value = 'ユーザー導線のE2Eテストです。';
    document.getElementById('threadForm').requestSubmit();
    await waitFor(() => document.getElementById('threads').textContent.includes('ブラウザからの戦略相談'), 'thread visible');
    checks.discussion = true;

    await go('tables');
    await waitFor(() => document.querySelector('[data-open-table="jj-table-a"]'), 'table A open');
    document.querySelector('[data-open-table="jj-table-a"]').click();
    await waitFor(() => !document.getElementById('pokerRoom').classList.contains('hidden') && document.querySelector('#seatLayer [data-seat="0"]'), 'poker room');
    document.querySelector('#seatLayer [data-seat="0"]').click();
    await waitFor(() => document.getElementById('seatLayer').textContent.includes('YOU'), 'seat confirmed');
    checks.pokerSeat = document.getElementById('roomTitle').textContent.includes('JJ Table A');
    document.getElementById('backLobby').click();
    await waitFor(() => !document.getElementById('lobbyPanel').classList.contains('hidden'), 'back lobby');

    checks.noHorizontalOverflow = document.documentElement.scrollWidth <= innerWidth + 2;

    if(innerWidth <= 700){
      document.querySelector('[data-mobile-more]').click();
      await waitFor(() => document.querySelector('[data-mobile-logout]'), 'mobile logout');
      document.querySelector('[data-mobile-logout]').click();
    }else{
      document.getElementById('headerLogoutBtn').click();
    }
    await waitFor(() => !document.getElementById('authView').classList.contains('hidden') && document.getElementById('appView').classList.contains('hidden'), 'logout');
    checks.logout = true;

    document.getElementById('loginName').value = 'ブラウザユーザー';
    document.getElementById('loginPin').value = '999999';
    document.getElementById('pinForm').requestSubmit();
    await waitFor(() =>
      !document.getElementById('authView').classList.contains('hidden') &&
      document.getElementById('appView').classList.contains('hidden') &&
      document.getElementById('toast').classList.contains('show') &&
      document.getElementById('toast').textContent.trim().length > 0,
      'wrong pin feedback'
    );
    checks.wrongPinRejected = true;

    document.getElementById('loginPin').value = '123456';
    document.getElementById('pinForm').requestSubmit();
    await waitFor(() => !document.getElementById('appView').classList.contains('hidden') && document.getElementById('userName').textContent === 'ブラウザユーザー', 'relogin');
    checks.relogin = true;
  }catch(error){
    checks.driverError = String(error && error.stack || error);
  }
  const ok = Object.values(checks).every(v => v === true);
  const pre = document.createElement('pre');
  pre.id = 'fullstackJourneyResult';
  pre.dataset.fullstackJourneyOk = ok ? '1' : '0';
  pre.textContent = JSON.stringify(checks);
  document.body.appendChild(pre);
})();
</script>
'''


def injected_index() -> str:
    text = (STATIC / "index.html").read_text(encoding="utf-8")
    assert "</body>" in text
    return text.replace("</body>", DRIVER + "</body>")


def build_test_app():
    # Avoid a smoke test normalizing checked-in admin assets in place.
    import admin_copy_patch

    admin_copy_patch.apply = lambda _path: None
    import app as production

    # Keep learning content deterministic and offline. The endpoint itself and
    # all production auth/routing still run normally.
    try:
        content = production.learning_content
        content._cache = content._fallback_payload()
        content._expires_at = float("inf")
        content._refreshing = False
    except Exception:
        pass

    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse

    @asynccontextmanager
    async def lifespan(_wrapper):
        async with production.app.router.lifespan_context(production.app):
            yield

    wrapper = FastAPI(lifespan=lifespan)

    @wrapper.get("/", include_in_schema=False)
    def root():
        return HTMLResponse(injected_index())

    wrapper.mount("/", production.app)
    return wrapper


def serve(port: int) -> None:
    import uvicorn

    app = build_test_app()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning", access_log=False)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_server(port: int, process: subprocess.Popen) -> None:
    url = f"http://127.0.0.1:{port}/api/health"
    last_error = None
    for _ in range(120):
        if process.poll() is not None:
            raise AssertionError(f"journey server exited early: {process.returncode}")
        try:
            with urllib.request.urlopen(url, timeout=0.5) as response:
                if response.status == 200:
                    return
        except Exception as exc:
            last_error = exc
        time.sleep(0.05)
    raise AssertionError(f"journey server did not become healthy: {last_error}")


def chrome_binary() -> str:
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        path = shutil.which(name)
        if path:
            return path
    raise AssertionError("Chrome/Chromium is required for full-stack user journey")


def run_viewport(width: int, height: int) -> None:
    chrome = chrome_binary()
    with tempfile.TemporaryDirectory(prefix="jj-fullstack-journey-") as td:
        work = Path(td)
        port = free_port()
        env = os.environ.copy()
        env.pop("DATABASE_URL", None)
        env.pop("RENDER", None)
        env["JJ_DB_PATH"] = str(work / "journey.sqlite3")
        env["JJ_ENABLE_DEMO_MEMBER"] = "0"
        env["JJ_ADMIN_NAME"] = "E2E_ADMIN"
        env.pop("JJ_ADMIN_PIN", None)
        process = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--serve", "--port", str(port)],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            wait_server(port, process)
            url = f"http://127.0.0.1:{port}/"
            last = ""
            for _ in range(2):
                proc = subprocess.run(
                    [
                        chrome,
                        "--headless",
                        "--no-sandbox",
                        "--disable-gpu",
                        "--run-all-compositor-stages-before-draw",
                        "--virtual-time-budget=30000",
                        f"--window-size={width},{height}",
                        "--dump-dom",
                        url,
                    ],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=70,
                )
                last = proc.stdout
                if 'data-fullstack-journey-ok="1"' in last:
                    break
            assert 'data-fullstack-journey-ok="1"' in last, last[-6000:]
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            if process.returncode not in (0, -15):
                output = process.stdout.read() if process.stdout else ""
                raise AssertionError(f"journey server failed: {process.returncode}\n{output[-3000:]}")


def main() -> None:
    run_viewport(1440, 900)
    run_viewport(390, 844)
    print("JJ_FULLSTACK_BROWSER_USER_JOURNEY_OK desktop=1 mobile=1")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    if args.serve:
        if not args.port:
            raise SystemExit("--port is required with --serve")
        serve(args.port)
    else:
        main()
