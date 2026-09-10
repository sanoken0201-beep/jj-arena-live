from __future__ import annotations

import py_compile
import sqlite3
import tempfile
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

import learning_content
import online_results_cleanup
from runtime_builder import RUNTIME_VERSION, build_runtime

ROOT = Path(__file__).resolve().parent
WORK = Path(tempfile.mkdtemp(prefix="jj-current-smoke-"))
DEST = build_runtime(WORK / "runtime")

server = (DEST / "server.py").read_text(encoding="utf-8")
db = (DEST / "db.py").read_text(encoding="utf-8")
appjs = (DEST / "static" / "app.js").read_text(encoding="utf-8")
css = (DEST / "static" / "styles.css").read_text(encoding="utf-8")
index = (DEST / "static" / "index.html").read_text(encoding="utf-8")
sw = (DEST / "static" / "sw.js").read_text(encoding="utf-8")

assert RUNTIME_VERSION == "1.20.2"
assert 'version="1.20.2"' in server or '"version":"1.20.2"' in server

# Quiz/ledger regression coverage from v1.18.6.
assert 'JJ_QUIZ_REWARD = 10' in server
assert 'CREATE TABLE IF NOT EXISTS quiz_attempts' in server
assert '@app.get("/api/quiz/question")' in server
assert '@app.post("/api/quiz/answer")' in server
assert '"quiz_reward"' in server
assert 'INSERT INTO point_ledger' in server
assert 'WHERE id=? AND user_id=? AND answer IS NULL' in server

# Mobile poker reliability regression coverage.
assert 'jjV186PreflopBaseBb' in appjs
assert 'base*multiplier' in appjs
assert 'jjV186ActionPending' in appjs
assert 'jjActionClock' in appjs
assert 'v1.18.6 poker interaction reliability' in css

# Tournament point-entry stacks must stay consistent across UI and server.
for value in (300, 400, 500, 600, 800, 1000):
    assert f"value:{value},label:'{value} / tournament'" in appjs
    assert f"value:{value},label:'{value} · Tournament'" in appjs
    assert f'{value}: "{value} / tournament"' in server
assert "else sel.value=String(game==='ring'?450:400)" in appjs

# Japanese-first learning share remains present.
assert 'v1.19.2 Japanese-first learning share' in appjs
assert '今日の学び' in appjs
assert '記事は日本語を優先' in appjs
assert "api('/learning-content')" in appjs
assert 'STRATEGY' in appjs and 'MOTIVATION' in appjs
assert 'v1.19.2 Japanese-first learning share' in css

# Member PIN self-service remains prominent and confirmed.
assert 'v1.19.3 member PIN self-service' in appjs
assert 'jj-account-security' in appjs
assert 'id="pinChangeConfirmForm"' in appjs
assert "post('/auth/change-pin',{current_pin:current,new_pin:next})" in appjs
assert '新しいPINが一致しません' in appjs
assert 'v1.19.3 member PIN self-service' in css

# v1.19.4 UI/accessibility baseline must survive later releases.
assert 'v1.19.4 UI foundation and accessibility' in appjs
assert 'jjV194UpdateConnectionStatus' in appjs
assert 'オフラインです。接続が戻るまで操作結果は確定しない場合があります。' in appjs
assert "actionBar.setAttribute('aria-label','ポーカー操作')" in appjs
assert "quiz.setAttribute('aria-label','クイズの回答候補')" in appjs
assert "rel.add('noopener');rel.add('noreferrer')" in appjs
assert 'v1.19.4 UI foundation and accessibility' in css
assert ':focus-visible' in css
assert 'min-height:44px' in css
assert 'prefers-reduced-motion:reduce' in css

# v1.20.0 player hand-history/analysis interface.
assert 'v1.20.0 private hand history and analytics' in appjs
assert "titles.analysis=['HAND REVIEW','ハンド分析']" in appjs
assert 'PRIVATE PERFORMANCE LAB' in appjs
assert 'id="jjAnalysisKpis"' in appjs
assert 'id="jjAnalysisTrend"' in appjs
assert 'id="jjAnalysisStats"' in appjs
assert 'id="jjAnalysisSignals"' in appjs
assert 'id="jjAnalysisPositions"' in appjs
assert 'id="jjAnalysisStacks"' in appjs
assert 'id="jjAnalysisSessions"' in appjs
assert 'id="jjHandList"' in appjs
assert '/analysis/summary' in appjs
assert '/analysis/hands?' in appjs
assert '/review' in appjs
assert 'PokerStars-style' not in appjs  # export formatting remains server-authoritative
assert '相手のホールカードはショーダウンで公開された場合だけ表示します' in appjs
assert 'v1.20.0 private hand history and analytics' in css
assert '.jj-replay-table' in css and '.jj-stat-grid' in css

# v1.20.1 keeps async filters coherent and prevents future showdown information
# from appearing in earlier replay frames.
assert 'v1.20.1 analysis request/replay stabilization' in appjs
assert 'analysisRequestSeq' in appjs
assert 'handRequestSeq' in appjs
assert "showdownVisible=phase==='complete'" in appjs
assert "p.in_hand?['??','??']:[]" in appjs

# v1.20.2 keeps bearer tokens out of WebSocket URLs and makes disconnect
# cleanup/timeout-loop failures observable without logging sensitive values.
assert 'v1.20.2 websocket token privacy' in appjs
assert "?token=${encodeURIComponent(token)}" not in appjs
assert "JSON.stringify({type:'auth',token})" in appjs
assert 'ws.query_params.get("token")' not in server
assert 'await asyncio.wait_for(ws.receive_text(), timeout=5.0)' in server
assert 'JJ_TIMEOUT_LOOP_ERROR' in server
assert 'JJ_WS_CONNECTION_ERROR' in server
assert '?v=47' in index
assert 'jj-arena-live-v47' in sw
assert 'request.url.query == "v=47"' in server

# Learning-content outbound security policy.
fallback = learning_content._fallback_payload()
assert fallback["policy"]["articles"] == "ja-first"
assert fallback["articles"] and fallback["videos"]
assert all(a["language"] == "ja" for a in fallback["articles"])
assert all(urlsplit(a["url"]).hostname == "japan.gtowizard.com" for a in fallback["articles"])
trusted_video_sources = {"GTO Wizard Japan", "ヨコサワポーカーチャンネル", "POKER BROTHERS"}
assert all(v["source"] in trusted_video_sources for v in fallback["videos"])
assert {v["category"] for v in fallback["videos"]} == {"strategy", "motivation"}
assert learning_content._safe_https_url("http://japan.gtowizard.com/blog/test/", {"japan.gtowizard.com"}) is None
assert learning_content._safe_https_url("https://evil.example/blog/test/", {"japan.gtowizard.com"}) is None

gto_feed = b'''<?xml version="1.0" encoding="UTF-8"?>
<rss><channel>
  <item><title>ICM\xe3\x81\xae\xe6\x97\xa5\xe6\x9c\xac\xe8\xaa\x9e\xe8\xa7\xa3\xe8\xaa\xac</title><link>https://japan.gtowizard.com/blog/icm-test/</link><pubDate>Thu, 10 Sep 2026 00:00:00 +0000</pubDate><category>ICM</category><description>Japanese poker article</description></item>
  <item><title>\xe6\x96\xb0\xe6\xa9\x9f\xe8\x83\xbd\xe3\x81\xae\xe3\x81\x8a\xe7\x9f\xa5\xe3\x82\x89\xe3\x81\x9b</title><link>https://japan.gtowizard.com/blog/news/product/</link><pubDate>Thu, 10 Sep 2026 01:00:00 +0000</pubDate></item>
  <item><title>English only title</title><link>https://japan.gtowizard.com/blog/english/</link><pubDate>Thu, 10 Sep 2026 02:00:00 +0000</pubDate></item>
</channel></rss>'''
parsed_articles = learning_content._parse_gtowizard_articles(gto_feed)
assert len(parsed_articles) == 1
assert parsed_articles[0]["title"] == "ICMの日本語解説"
assert parsed_articles[0]["topic"] == "ICM"

youtube_feed = b'''<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:yt="http://www.youtube.com/xml/schemas/2015">
 <entry><yt:videoId>abc123xyz00</yt:videoId><title>GTO\xe6\x88\xa6\xe7\x95\xa5\xe3\x81\xae\xe3\x83\x8f\xe3\x83\xb3\xe3\x83\x89\xe8\xa7\xa3\xe8\xaa\xac</title><link rel="alternate" href="https://www.youtube.com/watch?v=abc123xyz00"/><published>2026-09-10T00:00:00+00:00</published></entry>
 <entry><yt:videoId>def456xyz00</yt:videoId><title>\xe4\xb8\x96\xe7\x95\x8c\xe5\xa4\xa7\xe4\xbc\x9aWSOP\xe3\x81\xb8\xe6\x8c\x91\xe6\x88\xa6</title><link rel="alternate" href="https://www.youtube.com/watch?v=def456xyz00"/><published>2026-09-09T00:00:00+00:00</published></entry>
 <entry><yt:videoId>skip0000000</yt:videoId><title>\xe9\x9b\x91\xe8\xab\x87\xe9\x85\x8d\xe4\xbf\xa1</title><link rel="alternate" href="https://www.youtube.com/watch?v=skip0000000"/><published>2026-09-08T00:00:00+00:00</published></entry>
</feed>'''
parsed_videos = learning_content._parse_youtube_feed(youtube_feed, "POKER BROTHERS", "motivation")
assert len(parsed_videos) == 2
assert {v["category"] for v in parsed_videos} == {"strategy", "motivation"}
assert all(urlsplit(v["url"]).hostname == "www.youtube.com" for v in parsed_videos)

# Regression that caused the administrator lockout recovery failure.
assert '# v1.19.0 deterministic administrator recovery' in db
assert 'password_hash=? WHERE id=?' in db
assert 'DELETE FROM sessions WHERE user_id=?' in db
assert 'hash_password(pin)' in db

# Ranking cleanup stays one-time only.
class _CleanupTestDB:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    @staticmethod
    def utcnow() -> str:
        return "2026-09-10T00:00:00+00:00"


cleanup_db = _CleanupTestDB(WORK / "cleanup.sqlite")
with cleanup_db.connect() as con:
    con.execute("CREATE TABLE online_hand_results(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL)")
    con.executemany("INSERT INTO online_hand_results(id,user_id) VALUES (?,?)", [(1, 101), (2, 101), (3, 202)])
first_cleanup = online_results_cleanup.apply(cleanup_db)
assert first_cleanup == {"applied": True, "rows": 3, "users": 2}
with cleanup_db.connect() as con:
    assert con.execute("SELECT COUNT(*) AS c FROM online_hand_results").fetchone()["c"] == 0
    con.execute("INSERT INTO online_hand_results(id,user_id) VALUES (?,?)", (4, 303))
second_cleanup = online_results_cleanup.apply(cleanup_db)
assert second_cleanup == {"applied": False, "rows": 0, "users": 0}
with cleanup_db.connect() as con:
    assert con.execute("SELECT COUNT(*) AS c FROM online_hand_results").fetchone()["c"] == 1

# Production extension wiring.
app_source = (ROOT / "app.py").read_text(encoding="utf-8")
assert 'Production entrypoint for JJ Arena Live v1.20.2' in app_source
assert 'from runtime_builder import build_runtime' in app_source
assert 'DEST = build_runtime()' in app_source
assert 'online_results_cleanup.apply(db)' in app_source
assert 'admin_ledger_stabilization.install(app, admin_console)' in app_source
assert 'admin_pin_verification.install(app, admin_console)' in app_source
assert 'learning_content.install(app)' in app_source
assert 'hand_analytics.install(app, runtime_server, db)' in app_source
assert 'path.startswith("/api/analysis")' in app_source

# Hand analytics privacy, storage and API contract must remain server-side.
analytics_source = (ROOT / "hand_analytics.py").read_text(encoding="utf-8")
for table in ("jj_hand_history", "jj_hand_players", "jj_hand_actions", "jj_hand_snapshots", "jj_hand_reviews"):
    assert f"CREATE TABLE IF NOT EXISTS {table}" in analytics_source
assert 'Depends(server.current_user)' in analytics_source
assert 'if int(player["user_id"]) == int(viewer_id) or _as_int(player.get("went_showdown"))' in analytics_source
assert 'return ["??", "??"] if cards else []' in analytics_source
assert '"deck"' not in analytics_source[analytics_source.index('def _sanitize_state'):analytics_source.index('def _next_snapshot_seq')]
assert 'partial_capture' in analytics_source
assert 'PokerStars-style text export' in analytics_source
assert 'EVではありません' in analytics_source
assert 'SESSION_GAP_MINUTES = 30' in analytics_source
assert 'three_bet_opp' in analytics_source and 'cbet_opp' in analytics_source and 'steal_opp' in analytics_source

pin_verify_source = (ROOT / "admin_pin_verification.py").read_text(encoding="utf-8")
assert 'Depends(server.admin_user)' in pin_verify_source
assert 'VERIFY_MAX_ATTEMPTS = 5' in pin_verify_source
assert 'password_hash' in pin_verify_source
assert 'result="match" if matched else "no_match"' in pin_verify_source
assert 'candidate PIN or password hash' in pin_verify_source

admin_copy_source = (ROOT / "admin_copy_patch.py").read_text(encoding="utf-8")
assert 'admin_pin_verify.css' in admin_copy_source
assert 'admin_pin_verify.js' in admin_copy_source
assert 'admin_ui_foundation.css' in admin_copy_source
assert 'admin_ui_foundation.js' in admin_copy_source
assert '<th>アカウント</th><th>状態</th><th>ランキング</th>' in admin_copy_source
admin_pin_js = (ROOT / "admin_static" / "admin_pin_verify.js").read_text(encoding="utf-8")
assert 'type="password"' in admin_pin_js
assert '/verify-pin' in admin_pin_js
assert '現在のPINそのものは表示できません' in admin_pin_js
admin_ui_js = (ROOT / "admin_static" / "admin_ui_foundation.js").read_text(encoding="utf-8")
admin_ui_css = (ROOT / "admin_static" / "admin_ui_foundation.css").read_text(encoding="utf-8")
assert 'jjUserCount' in admin_ui_js and 'jjUserSearchClear' in admin_ui_js
assert "setAttribute('aria-current','page')" in admin_ui_js
assert 'lastUserOpener.focus' in admin_ui_js
assert ':focus-visible' in admin_ui_css and 'min-height:44px' in admin_ui_css
assert 'prefers-reduced-motion:reduce' in admin_ui_css and 'button[data-account-delete]' in admin_ui_css

ledger_patch = (ROOT / "admin_ledger_stabilization.py").read_text(encoding="utf-8")
assert "l.kind='quiz_reward'" in ledger_patch
assert "l.kind IN ('credit','collection','reversal')" in ledger_patch
assert '管理者による振込・回収だけを取消できます' in ledger_patch
assert 'row.update(categories)' in ledger_patch

for filename in [
    "runtime_builder.py", "v47_patch.py", "v46_patch.py", "v45_patch.py", "v44_patch.py", "v43_patch.py",
    "v42_patch.py", "v41_patch.py", "v40_patch.py", "v39_patch.py", "v38_patch.py", "hand_analytics.py",
    "hand_analytics_hardening.py", "learning_content.py", "admin_pin_verification.py", "admin_copy_patch.py",
    "admin_ledger_stabilization.py", "online_results_cleanup.py", "admin_delete.py", "smoke_test_user_management.py",
    "smoke_test_hand_analytics.py", "smoke_test_stat_definitions.py", "smoke_test_card_privacy.py",
    "smoke_test_hand_analytics_postgres_v2.py", "smoke_test_websocket_auth.py", "app.py",
]:
    py_compile.compile(str(ROOT / filename), doraise=True)

# Existing auth/account lifecycle regression remains part of every production build.
import smoke_test_user_management
smoke_test_user_management.run()

print("JJ_LEARNING_CONTENT_SMOKE_OK")
print("JJ_PIN_MANAGEMENT_SMOKE_OK")
print("JJ_UI_FOUNDATION_SMOKE_OK")
print("JJ_HAND_ANALYTICS_STATIC_OK")
print("JJ_ANALYSIS_STABILIZATION_SMOKE_OK")
print("JJ_WEBSOCKET_SECURITY_STATIC_OK")
print("JJ_ARENA_CURRENT_SMOKE_OK")
