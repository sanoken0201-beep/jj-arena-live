from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

from poker_connection_fix import apply_to_build
from served_assets import build_all
from smoke_test_poker_simple import HOOKS, state


EXTRA_HOOKS = r'''
  window.JJ_OOP_TEST={
    socketOpen(){jjV71SocketOpen(currentTableId)},
    disconnect(){jjV2SetConnection('reconnecting',false)},
    fresh(){return !!jjV2Connection.fresh},
    mode(){return jjV2Connection.mode},
    setSnapshot(s){
      api=async path=>{
        if(String(path).startsWith('/tables/'))return {state:structuredClone(s),messages:[]};
        throw new Error('unexpected test api '+path);
      };
    },
    sendImmediately(){
      post=async(path,body)=>{
        testSent.push({path,body});
        const next=structuredClone(tableState);
        next.legal={...(next.legal||{}),can_act:false};
        return next;
      };
    },
  };
'''


def oop_flop_state() -> dict:
    value = state(check=True, waiting=False, players=2)
    value["button_seat"] = 1  # Hero in seat 0 is OOP postflop heads-up.
    value["hand"]["phase"] = "flop"
    value["hand"]["action_seat"] = 0
    value["hand"]["board"] = ["4h", "3h", "9c"]
    value["hand"]["current_bet"] = 0
    value["seats"][0]["round_bet"] = 0
    value["seats"][1]["round_bet"] = 0
    value["legal"].update(
        {
            "can_act": True,
            "can_check": True,
            "can_call": False,
            "can_raise": True,
            "can_all_in": True,
            "call_amount": 0,
            "min_raise_to": 100,
            "max_raise_to": 14950,
        }
    )
    return value


def main() -> None:
    chrome = next(
        (
            shutil.which(name)
            for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")
            if shutil.which(name)
        ),
        None,
    )
    assert chrome, "Chrome is required"

    with tempfile.TemporaryDirectory(prefix="jj-oop-check-browser-") as directory, sync_playwright() as p:
        root = Path(directory)
        manifest = build_all(root)
        apply_to_build(root, manifest)

        js_path = root / "static/app.js"
        js = js_path.read_text(encoding="utf-8")
        assert js.count("  init();") == 1
        js = js.replace("  init();", "  bind();", 1)
        end = js.rfind("})();")
        assert end > 0
        js = js[:end] + HOOKS + EXTRA_HOOKS + js[end:]
        js_path.write_text(js, encoding="utf-8")

        html_path = root / "index.html"
        html_path.write_text(
            html_path.read_text(encoding="utf-8").replace('"/static/', '"static/'),
            encoding="utf-8",
        )

        browser = p.chromium.launch(
            executable_path=chrome,
            headless=True,
            args=["--no-sandbox", "--allow-file-access-from-files"],
        )
        try:
            for width, height in ((1366, 768), (390, 844)):
                page = browser.new_page(viewport={"width": width, "height": height})
                errors: list[str] = []
                page.on("pageerror", lambda err: errors.append(str(err)))
                page.goto(html_path.resolve().as_uri())
                page.wait_for_function("!!window.JJ_TEST && !!window.JJ_OOP_TEST")

                snapshot = oop_flop_state()
                page.evaluate("s=>JJ_TEST.setState(s)", snapshot)
                check = page.locator('#actionBar [data-action="check"]')
                check.wait_for(state="visible")
                assert page.evaluate("JJ_OOP_TEST.fresh()")
                assert check.is_enabled(), (width, height, "baseline OOP check disabled")

                # Reproduce the production handoff: HTTP state is fresh, then
                # WebSocket opens before its first state frame arrives. CHECK
                # must remain usable during this brief transition.
                page.evaluate("JJ_OOP_TEST.sendImmediately()")
                before = page.evaluate("JJ_TEST.sent.length")
                page.evaluate("JJ_OOP_TEST.socketOpen()")
                assert page.evaluate("JJ_OOP_TEST.fresh()"), (width, height, "WS open discarded fresh HTTP state")
                assert check.is_enabled(), (width, height, "OOP check disabled on WS open")
                check.click()
                page.wait_for_function(f"JJ_TEST.sent.length==={before + 1}")
                assert page.evaluate("JJ_TEST.sent.at(-1).body.action") == "check"

                # A real disconnect must still fail closed. On the next socket
                # open, if no WS frame arrives, the 700ms watchdog performs an
                # authoritative HTTP refresh and restores legal actions.
                page.evaluate("s=>JJ_TEST.setState(s)", snapshot)
                check = page.locator('#actionBar [data-action="check"]')
                assert check.is_enabled()
                page.evaluate("JJ_OOP_TEST.disconnect()")
                assert not page.evaluate("JJ_OOP_TEST.fresh()")
                assert check.is_disabled(), (width, height, "disconnect did not disable stale action")

                page.evaluate("s=>JJ_OOP_TEST.setSnapshot(s)", snapshot)
                page.evaluate("JJ_OOP_TEST.socketOpen()")
                page.wait_for_function("JJ_OOP_TEST.fresh()", timeout=2500)
                check = page.locator('#actionBar [data-action="check"]')
                assert check.is_enabled(), (width, height, "HTTP watchdog did not restore OOP check")
                assert not errors, errors
                page.close()
        finally:
            browser.close()

    print("JJ_OOP_CHECK_BROWSER_OK")


if __name__ == "__main__":
    main()
