from __future__ import annotations

import copy
import email.utils
import html
import re
import threading
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import urlsplit

from fastapi import Depends


CACHE_SECONDS = 6 * 60 * 60
FETCH_TIMEOUT = 3.0
MAX_RESPONSE_BYTES = 1_500_000
GTO_WIZARD_JP_FEED = "https://japan.gtowizard.com/blog/feed/"
YOUTUBE_FEED = "https://www.youtube.com/feeds/videos.xml?channel_id={}"

TRUSTED_YOUTUBE_CHANNELS = (
    {
        "name": "ヨコサワポーカーチャンネル",
        "channel_id": "UCuhdzbvkmR75piBs4VsMFMA",
        "default_category": "strategy",
    },
    {
        "name": "POKER BROTHERS",
        "channel_id": "UCispM9GhGBT5XUC5VbLNl6Q",
        "default_category": "motivation",
    },
)

ARTICLE_FALLBACK = (
    {
        "title": "リンプポットをどうプレイするか",
        "url": "https://japan.gtowizard.com/blog/is-limping-pimping/",
        "source": "GTO Wizard Japan",
        "language": "ja",
        "published_at": "2026-08-22T00:00:00+09:00",
        "topic": "エクスプロイト / 理論",
        "summary": "日本語で読めるGTO Wizard公式記事。リンプポットへの対応をスタック別に整理します。",
    },
    {
        "title": "バブルとFTバブルの違い",
        "url": "https://japan.gtowizard.com/blog/money-bubble-vs-final-table-bubble/",
        "source": "GTO Wizard Japan",
        "language": "ja",
        "published_at": "2026-08-09T00:00:00+09:00",
        "topic": "ICM / トーナメント",
        "summary": "バブルとファイナルテーブル・バブルで戦略がどう変わるかを扱う日本語記事です。",
    },
    {
        "title": "なぜ自分のソリューションはGTO Wizardと違うのか？",
        "url": "https://japan.gtowizard.com/blog/why-doesnt-my-solution-match-gto-wizard/",
        "source": "GTO Wizard Japan",
        "language": "ja",
        "published_at": "2026-08-09T00:00:00+09:00",
        "topic": "GTO / ソルバー",
        "summary": "ソルバー間の差や入力条件による解の変化を理解するための日本語記事です。",
    },
    {
        "title": "GTO Wizardになる方法",
        "url": "https://japan.gtowizard.com/blog/how-to-become-a-gto-wizard/",
        "source": "GTO Wizard Japan",
        "language": "ja",
        "published_at": "2023-12-01T00:00:00+09:00",
        "topic": "学習法",
        "summary": "GTO学習を体系的に進めるための公式ガイドです。",
    },
)

VIDEO_FALLBACK = (
    {
        "title": "Axoの正しいプレイ",
        "url": "https://youtu.be/PkIcmLym2w8",
        "video_id": "PkIcmLym2w8",
        "source": "GTO Wizard Japan",
        "category": "strategy",
        "published_at": "2026-06-14T00:00:00+09:00",
        "reason": "GTO Wizard Japan公式の日本語戦略解説",
    },
    {
        "title": "MTTソリューションの使い方",
        "url": "https://youtu.be/EHDtuke1ug8",
        "video_id": "EHDtuke1ug8",
        "source": "GTO Wizard Japan",
        "category": "strategy",
        "published_at": "2025-11-06T00:00:00+09:00",
        "reason": "GTO Wizard Japan公式の日本語ツール解説",
    },
    {
        "title": "世界トッププロたちが愛用する『GTO Wizard』の使い方",
        "url": "https://www.youtube.com/watch?v=l0v4YOmayjA",
        "video_id": "l0v4YOmayjA",
        "source": "ヨコサワポーカーチャンネル",
        "category": "strategy",
        "published_at": "2024-04-13T00:00:00+09:00",
        "reason": "国内プロによる日本語のGTO Wizard解説",
    },
    {
        "title": "ChatGPTの力を借りてGTOウィザード完全制覇を目指す！！",
        "url": "https://www.youtube.com/watch?v=GppbUZp6qT8",
        "video_id": "GppbUZp6qT8",
        "source": "POKER BROTHERS",
        "category": "motivation",
        "published_at": "2026-02-28T00:00:00+09:00",
        "reason": "継続学習をテーマにした国内プレイヤーの企画",
    },
    {
        "title": "最後のハンドが衝撃すぎる…【TRITON JEJU 2026】",
        "url": "https://www.youtube.com/watch?v=Vss3HbjtL9M",
        "video_id": "Vss3HbjtL9M",
        "source": "POKER BROTHERS",
        "category": "motivation",
        "published_at": "2026-03-23T00:00:00+09:00",
        "reason": "ハイレベルなトーナメント挑戦を追えるモチベーション動画",
    },
)

STRATEGY_WORDS = (
    "gto", "wizard", "解説", "戦略", "上達", "勉強", "学習", "ハンド", "レンジ",
    "プリフロップ", "ポストフロップ", "ブラフ", "icm", "mtt", "キャッシュ", "トーナメント",
    "ファイナル", "ベット", "レイズ", "レビュー", "ソルバー",
)
MOTIVATION_WORDS = (
    "triton", "wsop", "wpt", "apt", "優勝", "世界", "大会", "挑戦", "賞金", "ファイナル",
    "day", "結果", "インマネ", "high roller", "ハイローラー", "逆転", "遠征",
)

_cache_lock = threading.Lock()
_cache: dict = {}
_expires_at = 0.0
_refreshing = False


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _thumbnail(video_id: str) -> str:
    return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg" if video_id else ""


def _with_thumbnails(videos: list[dict]) -> list[dict]:
    out = []
    for video in videos:
        item = dict(video)
        item["thumbnail"] = _thumbnail(str(item.get("video_id") or ""))
        out.append(item)
    return out


def _fallback_payload() -> dict:
    return {
        "updated_at": _now_iso(),
        "articles": [dict(x) for x in ARTICLE_FALLBACK],
        "videos": _with_thumbnails([dict(x) for x in VIDEO_FALLBACK[:5]]),
        "policy": {
            "articles": "ja-first",
            "article_source": "GTO Wizard Japan",
            "video_sources": ["GTO Wizard Japan", "ヨコサワポーカーチャンネル", "POKER BROTHERS"],
            "stale_while_revalidate": True,
        },
    }


def _safe_https_url(url: str, allowed_hosts: set[str]) -> str | None:
    try:
        parsed = urlsplit((url or "").strip())
    except Exception:
        return None
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or host not in allowed_hosts:
        return None
    return parsed.geturl()


def _fetch_bytes(url: str) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "JJ-Arena-Learning/1.19.2 (+https://jj-arena-live.onrender.com)",
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9, */*;q=0.5",
        },
    )
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as response:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("learning feed too large")
    return raw


def _clean_text(value: str | None, limit: int = 180) -> str:
    value = html.unescape(re.sub(r"<[^>]+>", " ", value or ""))
    value = re.sub(r"\s+", " ", value).strip()
    return value[:limit]


def _published_iso(value: str | None) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    try:
        dt = email.utils.parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except Exception:
        pass
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
    except Exception:
        return ""


def _has_japanese(text: str) -> bool:
    return bool(re.search(r"[ぁ-んァ-ヶ一-龠々ー]", text or ""))


def _article_topic(item: ET.Element) -> str:
    categories = [_clean_text(x.text, 40) for x in item.findall("category") if _clean_text(x.text, 40)]
    return " / ".join(categories[:2]) or "ポーカー戦略"


def _parse_gtowizard_articles(raw: bytes) -> list[dict]:
    root = ET.fromstring(raw)
    results: list[dict] = []
    for item in root.findall(".//item"):
        title = _clean_text(item.findtext("title"), 150)
        url = _safe_https_url(item.findtext("link") or "", {"japan.gtowizard.com"})
        if not title or not url or not _has_japanese(title):
            continue
        path = urlsplit(url).path.lower()
        if "/blog/news/" in path or "/blog/videos" in path:
            continue
        description = _clean_text(item.findtext("description"), 180)
        results.append(
            {
                "title": title,
                "url": url,
                "source": "GTO Wizard Japan",
                "language": "ja",
                "published_at": _published_iso(item.findtext("pubDate")),
                "topic": _article_topic(item),
                "summary": description,
            }
        )
    results.sort(key=lambda x: x.get("published_at") or "", reverse=True)
    return _dedupe(results, "url")[:6]


def _parse_youtube_feed(raw: bytes, source: str, default_category: str) -> list[dict]:
    root = ET.fromstring(raw)
    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "yt": "http://www.youtube.com/xml/schemas/2015",
    }
    videos: list[dict] = []
    for entry in root.findall("atom:entry", ns):
        title = _clean_text(entry.findtext("atom:title", default="", namespaces=ns), 160)
        video_id = _clean_text(entry.findtext("yt:videoId", default="", namespaces=ns), 32)
        link_node = entry.find("atom:link[@rel='alternate']", ns)
        link = link_node.get("href", "") if link_node is not None else ""
        url = _safe_https_url(link, {"www.youtube.com", "youtube.com", "youtu.be"})
        if not title or not video_id or not url:
            continue
        lower = title.lower()
        strategy_score = sum(1 for word in STRATEGY_WORDS if word in lower)
        motivation_score = sum(1 for word in MOTIVATION_WORDS if word in lower)
        if strategy_score == 0 and motivation_score == 0:
            continue
        category = "strategy" if strategy_score >= motivation_score else "motivation"
        if strategy_score == motivation_score:
            category = default_category
        reason = (
            "信頼できる国内チャンネルの戦略・学習コンテンツ"
            if category == "strategy"
            else "大会・挑戦を追えるモチベーションコンテンツ"
        )
        videos.append(
            {
                "title": title,
                "url": url,
                "video_id": video_id,
                "source": source,
                "category": category,
                "published_at": _published_iso(entry.findtext("atom:published", default="", namespaces=ns)),
                "reason": reason,
                "_score": max(strategy_score, motivation_score),
            }
        )
    videos.sort(key=lambda x: (int(x.get("_score") or 0), x.get("published_at") or ""), reverse=True)
    for item in videos:
        item.pop("_score", None)
    return videos


def _dedupe(items: list[dict], field: str) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for item in items:
        key = str(item.get(field) or "")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _choose_videos(dynamic: list[dict]) -> list[dict]:
    all_items = _dedupe(dynamic + [dict(x) for x in VIDEO_FALLBACK], "url")
    strategies = [x for x in all_items if x.get("category") == "strategy"]
    motivations = [x for x in all_items if x.get("category") == "motivation"]
    strategies.sort(key=lambda x: x.get("published_at") or "", reverse=True)
    motivations.sort(key=lambda x: x.get("published_at") or "", reverse=True)
    selected = strategies[:3] + motivations[:2]
    return _with_thumbnails(_dedupe(selected, "url")[:5])


def _refresh_payload() -> dict:
    base = _fallback_payload()
    articles: list[dict] = []
    dynamic_videos: list[dict] = []

    try:
        articles = _parse_gtowizard_articles(_fetch_bytes(GTO_WIZARD_JP_FEED))
    except Exception:
        articles = []

    for channel in TRUSTED_YOUTUBE_CHANNELS:
        try:
            raw = _fetch_bytes(YOUTUBE_FEED.format(channel["channel_id"]))
            dynamic_videos.extend(
                _parse_youtube_feed(raw, channel["name"], channel["default_category"])
            )
        except Exception:
            continue

    if articles:
        articles = _dedupe(articles + [dict(x) for x in ARTICLE_FALLBACK], "url")[:6]
    else:
        articles = base["articles"]

    return {
        "updated_at": _now_iso(),
        "articles": articles,
        "videos": _choose_videos(dynamic_videos),
        "policy": base["policy"],
    }


def _refresh_worker() -> None:
    global _cache, _expires_at, _refreshing
    try:
        payload = _refresh_payload()
        with _cache_lock:
            _cache = payload
            _expires_at = time.monotonic() + CACHE_SECONDS
    finally:
        with _cache_lock:
            _refreshing = False


def get_learning_content() -> dict:
    global _cache, _refreshing
    start_refresh = False
    with _cache_lock:
        if not _cache:
            _cache = _fallback_payload()
        if time.monotonic() >= _expires_at and not _refreshing:
            _refreshing = True
            start_refresh = True
        payload = copy.deepcopy(_cache)
    if start_refresh:
        threading.Thread(target=_refresh_worker, name="jj-learning-refresh", daemon=True).start()
    return payload


def install(app) -> None:
    if getattr(app.state, "jj_learning_content_installed", False):
        return
    app.state.jj_learning_content_installed = True

    import server

    @app.get("/api/learning-content", include_in_schema=False)
    def learning_content(user=Depends(server.current_user)):
        return get_learning_content()
