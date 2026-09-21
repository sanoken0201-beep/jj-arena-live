from __future__ import annotations

from served_assets import ASSET_VERSION, build_app_js, build_index, build_service_worker, build_styles


def main() -> None:
    assert ASSET_VERSION == 72

    index = build_index()
    js = build_app_js()
    css = build_styles()
    worker = build_service_worker()

    assert f"/static/app.js?v={ASSET_VERSION}" in index
    assert f"/static/styles.css?v={ASSET_VERSION}" in index

    marker = "v69 pwa update prompt 2026-09-13"
    assert marker in js
    assert marker in css
    assert "新しいバージョンがあります" in js
    assert "ハンド中でない時に更新してください。" in js
    assert "jjUpdateRequested=true" in js
    assert "reg.waiting.postMessage({type:'SKIP_WAITING'})" in js
    assert "if(!jjUpdateRequested||jjUpdateReloading)return" in js
    assert "location.reload()" in js
    assert "reg.update().catch(()=>{})" in js
    assert "jj-update-banner" in css

    assert f"const CACHE='jj-arena-live-v{ASSET_VERSION}';" in worker
    assert f"'/static/styles.css?v={ASSET_VERSION}'" in worker
    assert f"'/static/app.js?v={ASSET_VERSION}'" in worker
    assert "self.addEventListener('install',e=>{e.waitUntil" in worker
    assert "install',e=>{self.skipWaiting()" not in worker
    assert "e.data.type==='SKIP_WAITING'" in worker
    assert "self.skipWaiting()" in worker

    # Authenticated/dynamic traffic must never be written to Cache Storage.
    # The application shell and static assets may be cached; API and WebSocket
    # paths are explicitly bypassed before any respondWith/cache.put branch.
    assert "e.request.method!=='GET'||u.pathname.startsWith('/api/')||u.pathname.startsWith('/ws/')" in worker
    api_guard = worker.index("u.pathname.startsWith('/api/')")
    cache_write = worker.index("c.put(e.request,copy)")
    assert api_guard < cache_write

    print("JJ_PWA_UPDATE_OK")


if __name__ == "__main__":
    main()
