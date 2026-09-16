from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

from poker_connection_fix import apply_to_build as apply_connection_fix
from poker_control_safety import apply_to_build as apply_control_safety
from served_assets import build_all
from smoke_test_poker_simple import HOOKS, state


AUDIT_HOOKS = r'''
  const jjAuditCalls=[];
  let jjAuditPending=[];
  window.JJ_CONTROL_AUDIT={
    calls:jjAuditCalls,
    clear(){jjAuditCalls.length=0;jjAuditPending=[]},
    rejectPost(){
      post=async(path,body)=>{jjAuditCalls.push({path,body});throw new Error('audit failure')};
    },
    deferPost(){
      post=async(path,body)=>{
        jjAuditCalls.push({path,body});
        return await new Promise((resolve,reject)=>jjAuditPending.push({resolve,reject}));
      };
    },
    immediatePost(){
      post=async(path,body)=>{
        jjAuditCalls.push({path,body});
        if(String(path).endsWith('/action')){
          const next=structuredClone(tableState);next.legal={...(next.legal||{}),can_act:false};return next;
        }
        return {ok:true,state:structuredClone(tableState),status:'reserved'};
      };
    },
  };
'''


def waiting_state() -> dict:
    value = state(check=False, waiting=True, players=2)
    value["status"] = "waiting"
    value["session_active"] = False
    value["hand"] = None
    value["legal"] = {"can_act": False}
    value["seats"][0].update({"ready": False, "in_hand": False, "round_bet": 0, "contributed": 0})
    value["seats"][1].update({"ready": False, "in_hand": False, "round_bet": 0, "contributed": 0})
    return value


def between_hands_state() -> dict:
    value = waiting_state()
    value["session_active"] = True
    return value


def main() -> None:
    chrome = next((shutil.which(name) for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser") if shutil.which(name)), None)
    assert chrome, "Chrome is required"
    failures: list[str] = []

    with tempfile.TemporaryDirectory(prefix="jj-control-audit-") as directory, sync_playwright() as p:
        root = Path(directory)
        manifest = build_all(root)
        manifest = apply_connection_fix(root, manifest)
        apply_control_safety(root, manifest)

        js_path = root / "static/app.js"
        js = js_path.read_text(encoding="utf-8")
        assert js.count("  init();") == 1
        js = js.replace("  init();", "  bind();", 1)
        end = js.rfind("})();")
        assert end > 0
        js_path.write_text(js[:end] + HOOKS + AUDIT_HOOKS + js[end:], encoding="utf-8")

        html_path = root / "index.html"
        html_path.write_text(html_path.read_text(encoding="utf-8").replace('"/static/', '"static/'), encoding="utf-8")

        browser = p.chromium.launch(executable_path=chrome, headless=True, args=["--no-sandbox", "--allow-file-access-from-files"])
        try:
            for width, height in ((1366, 768), (390, 844)):
                page = browser.new_page(viewport={"width": width, "height": height})
                errors: list[str] = []
                page.on("pageerror", lambda err: errors.append(str(err)))
                page.goto(html_path.resolve().as_uri())
                page.wait_for_function("!!window.JJ_TEST && !!window.JJ_CONTROL_AUDIT")

                for action, check in (("fold", False), ("call", False), ("check", True)):
                    page.evaluate("s=>JJ_TEST.setState(s)", state(check=check))
                    button = page.locator(f'#actionBar [data-action="{action}"]')
                    assert button.count() == 1 and button.is_enabled(), (width, height, action)

                page.evaluate("s=>JJ_TEST.setState(s)", waiting_state())
                page.evaluate("JJ_CONTROL_AUDIT.clear();JJ_CONTROL_AUDIT.rejectPost()")
                ready = page.locator("#jjReadyBtn")
                ready.click(); page.wait_for_timeout(80)
                if ready.is_disabled(): failures.append(f"{width}x{height}: READY remains disabled after failed request")

                page.evaluate("s=>JJ_TEST.setState(s)", between_hands_state())
                page.evaluate("JJ_CONTROL_AUDIT.clear();JJ_CONTROL_AUDIT.deferPost()")
                sitout = page.locator('[data-table-presence="sitout"]')
                sitout.click()
                if sitout.is_enabled(): sitout.click()
                page.wait_for_timeout(40)
                calls = page.evaluate("JJ_CONTROL_AUDIT.calls.filter(x=>String(x.path).endsWith('/presence')).length")
                if calls != 1: failures.append(f"{width}x{height}: sit-out fast double tap sent {calls} requests")

                leave_state = waiting_state(); leave_state["seats"][0]["sitting_out"] = True
                page.evaluate("s=>JJ_TEST.setState(s)", leave_state)
                page.evaluate("JJ_CONTROL_AUDIT.clear();JJ_CONTROL_AUDIT.deferPost()")
                leave = page.locator("#leaveSeatBtn")
                leave.click()
                if leave.is_enabled(): leave.click()
                page.wait_for_timeout(40)
                calls = page.evaluate("JJ_CONTROL_AUDIT.calls.filter(x=>String(x.path).endsWith('/leave')).length")
                if calls != 1: failures.append(f"{width}x{height}: immediate leave fast double tap sent {calls} requests")

                page.evaluate("s=>JJ_TEST.setState(s)", state(check=False))
                page.evaluate("JJ_CONTROL_AUDIT.clear();JJ_CONTROL_AUDIT.immediatePost()")
                raise_button = page.locator('#actionBar [data-action="raise"]')
                page.locator("#raiseTo").fill("150")
                raise_button.click()
                assert page.evaluate("JJ_CONTROL_AUDIT.calls.length") == 0
                assert raise_button.evaluate("el=>el.classList.contains('jj-confirm-allin')")
                page.evaluate("JJ_TEST.render()")
                raise_button = page.locator('#actionBar [data-action="raise"]')
                page.locator("#raiseTo").fill("150")
                raise_button.click(); page.wait_for_timeout(40)
                if page.evaluate("JJ_CONTROL_AUDIT.calls.length") != 0:
                    failures.append(f"{width}x{height}: all-in confirmation survived a control rerender")

                failures.extend(f"{width}x{height}: page error: {err}" for err in errors)
                page.close()
        finally:
            browser.close()

    if failures:
        print("JJ_POKER_CONTROL_AUDIT_FOUND")
        for item in failures: print("ISSUE", item)
        raise SystemExit(1)
    print("JJ_POKER_CONTROL_AUDIT_OK")


if __name__ == "__main__":
    main()

