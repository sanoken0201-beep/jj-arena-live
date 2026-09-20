from __future__ import annotations

"""Real-Chromium recovery-state regression for the public Ring client.

This test does not claim to emulate a carrier network or a physical handset.
It exercises the production browser bundle through the same state transitions
that a WebSocket loss, HTTP fallback, and authoritative recovery use in
production. Both desktop and mobile viewports are covered.
"""

import shutil
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

from browser_asset_pipeline import finalize_build
from served_assets import build_all
from smoke_test_poker_simple import HOOKS, state


NETWORK_HOOKS = r'''
  window.JJ_NETWORK_RECOVERY={
    resetTelemetry(){
      if(jjV6Telemetry.timer){clearTimeout(jjV6Telemetry.timer);jjV6Telemetry.timer=null}
      jjV6Telemetry.queue.length=0;
      jjV6Telemetry.hadDisconnect=false;
      jjV6Telemetry.awaitingFresh=false;
    },
    events(){
      return jjV6Telemetry.queue.map(x=>({event:x.event,detail:x.detail}));
    },
    fresh(){return !!jjV2Connection.fresh},
    mode(){return String(jjV2Connection.mode||'')},
    disconnect(){
      jjV6ConnectionClosed();
      jjV2SetConnection('reconnecting',false);
      renderPokerRoom();
    },
    socketOpen(){
      jjV6ConnectionOpen();
      jjV2SetConnection('syncing',false);
      renderPokerRoom();
    },
    accept(s,source='poll'){
      const previous=tableState;
      tableState=structuredClone(s);
      jjV2AcceptState(source,previous);
      renderPokerRoom();
    },
  };
'''


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

    with tempfile.TemporaryDirectory(prefix="jj-network-recovery-") as directory, sync_playwright() as p:
        root = Path(directory)
        manifest = build_all(root)
        finalize_build(root, manifest)

        js_path = root / "static/app.js"
        js = js_path.read_text(encoding="utf-8")
        assert js.count("  init();") == 1
        js = js.replace("  init();", "  bind();", 1)
        end = js.rfind("})();")
        assert end > 0
        js_path.write_text(js[:end] + HOOKS + NETWORK_HOOKS + js[end:], encoding="utf-8")

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
        failures: list[str] = []
        try:
            for width, height in ((1366, 768), (390, 844)):
                page = browser.new_page(viewport={"width": width, "height": height})
                errors: list[str] = []
                page.on("pageerror", lambda err: errors.append(str(err)))
                page.goto(html_path.resolve().as_uri())
                page.wait_for_function("!!window.JJ_TEST && !!window.JJ_NETWORK_RECOVERY")

                snapshot = state(check=True, waiting=False, players=2)
                page.evaluate("s=>JJ_TEST.setState(s)", snapshot)
                check = page.locator('#actionBar [data-action="check"]')
                check.wait_for(state="visible")
                if not check.is_enabled():
                    failures.append(f"{width}x{height}: baseline CHECK disabled")

                page.evaluate("JJ_NETWORK_RECOVERY.resetTelemetry()")

                # Real disconnect boundary: stale state must fail closed before
                # either the socket or fallback path has recovered.
                page.evaluate("JJ_NETWORK_RECOVERY.disconnect()")
                if page.evaluate("JJ_NETWORK_RECOVERY.fresh()"):
                    failures.append(f"{width}x{height}: disconnect left state fresh")
                if not check.is_disabled():
                    failures.append(f"{width}x{height}: stale CHECK remained enabled")
                events = page.evaluate("JJ_NETWORK_RECOVERY.events()")
                if events.count({"event": "fallback", "detail": "ws_close"}) != 1:
                    failures.append(f"{width}x{height}: ws_close telemetry missing/duplicated: {events}")

                # Socket open alone is not recovery. Controls remain fail-closed
                # until a fresh authoritative state has actually been accepted.
                page.evaluate("JJ_NETWORK_RECOVERY.socketOpen()")
                if page.evaluate("JJ_NETWORK_RECOVERY.fresh()"):
                    failures.append(f"{width}x{height}: WS open incorrectly marked state fresh")
                if not check.is_disabled():
                    failures.append(f"{width}x{height}: CHECK enabled before fresh state")
                events = page.evaluate("JJ_NETWORK_RECOVERY.events()")
                if events.count({"event": "reconnect", "detail": "ws_open"}) != 1:
                    failures.append(f"{width}x{height}: ws_open telemetry missing/duplicated: {events}")
                if {"event": "reconnect", "detail": "fresh_state"} in events:
                    failures.append(f"{width}x{height}: fresh_state emitted before recovery")

                # HTTP fallback can restore an authoritative snapshot. This is
                # the point at which actions may become usable again.
                page.evaluate("(s)=>JJ_NETWORK_RECOVERY.accept(s,'poll')", snapshot)
                check = page.locator('#actionBar [data-action="check"]')
                if not page.evaluate("JJ_NETWORK_RECOVERY.fresh()"):
                    failures.append(f"{width}x{height}: fallback did not restore fresh state")
                if not check.is_enabled():
                    failures.append(f"{width}x{height}: CHECK not restored after fresh fallback")
                events = page.evaluate("JJ_NETWORK_RECOVERY.events()")
                if events.count({"event": "reconnect", "detail": "fresh_state"}) != 1:
                    failures.append(f"{width}x{height}: fresh recovery telemetry missing/duplicated: {events}")

                # Repeated authoritative frames after the same outage must not
                # inflate successful-recovery counts.
                page.evaluate("(s)=>JJ_NETWORK_RECOVERY.accept(s,'ws')", snapshot)
                events = page.evaluate("JJ_NETWORK_RECOVERY.events()")
                if events.count({"event": "reconnect", "detail": "fresh_state"}) != 1:
                    failures.append(f"{width}x{height}: recovery telemetry double-counted: {events}")

                # A second outage is a separate recovery cycle and must be
                # independently fail-closed and independently counted.
                page.evaluate("JJ_NETWORK_RECOVERY.disconnect()")
                if not check.is_disabled():
                    failures.append(f"{width}x{height}: second outage did not disable action")
                page.evaluate("(s)=>JJ_NETWORK_RECOVERY.accept(s,'poll')", snapshot)
                events = page.evaluate("JJ_NETWORK_RECOVERY.events()")
                if events.count({"event": "fallback", "detail": "ws_close"}) != 2:
                    failures.append(f"{width}x{height}: second disconnect not counted: {events}")
                if events.count({"event": "reconnect", "detail": "fresh_state"}) != 2:
                    failures.append(f"{width}x{height}: second recovery not counted: {events}")
                if not page.locator('#actionBar [data-action="check"]').is_enabled():
                    failures.append(f"{width}x{height}: action not restored after second recovery")

                if not page.evaluate("document.documentElement.scrollWidth<=innerWidth+2"):
                    failures.append(f"{width}x{height}: horizontal overflow during recovery")
                failures.extend(f"{width}x{height}: page error: {err}" for err in errors)
                page.close()
        finally:
            browser.close()

    if failures:
        print("JJ_NETWORK_RECOVERY_BROWSER_FOUND")
        for item in failures:
            print("ISSUE", item)
        raise SystemExit(1)
    print("JJ_NETWORK_RECOVERY_BROWSER_OK desktop=1 mobile=1 cycles=2")


if __name__ == "__main__":
    main()
