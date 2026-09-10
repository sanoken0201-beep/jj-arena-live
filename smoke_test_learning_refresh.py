from __future__ import annotations

from urllib.parse import urlsplit

import learning_content
import learning_content_refresh


def run() -> None:
    old_articles = learning_content.ARTICLE_FALLBACK
    old_cache_seconds = learning_content.CACHE_SECONDS
    old_cache = dict(learning_content._cache)
    old_expiry = learning_content._expires_at
    old_refreshing = learning_content._refreshing
    try:
        learning_content._cache = {"stale": True}
        learning_content._expires_at = 999999999.0
        learning_content._refreshing = True
        learning_content_refresh.apply(learning_content)

        assert learning_content.CACHE_SECONDS == 3600
        assert learning_content._cache == {}
        assert learning_content._expires_at == 0.0
        assert learning_content._refreshing is False

        payload = learning_content._fallback_payload()
        articles = payload["articles"]
        assert len(articles) == 6
        assert all(article["language"] == "ja" for article in articles)
        assert all(article["source"] == "GTO Wizard Japan" for article in articles)
        assert all(urlsplit(article["url"]).hostname == "japan.gtowizard.com" for article in articles)
        assert min(article["published_at"] for article in articles) >= "2026-08-04"
        assert "GTO Wizardになる方法" not in {article["title"] for article in articles}
        assert "プロファイル別エクスプロイト 第3回｜マニアック" in {article["title"] for article in articles}
        assert "IPでドローをベットする本当の基準" in {article["title"] for article in articles}

        # Live parsing remains Japanese-only and is still allowed to supersede
        # these fallbacks as newer GTO Wizard Japan RSS entries arrive.
        assert payload["policy"]["articles"] == "ja-first"
        assert payload["policy"]["article_source"] == "GTO Wizard Japan"

        print("JJ_LEARNING_REFRESH_SMOKE_OK")
    finally:
        learning_content.ARTICLE_FALLBACK = old_articles
        learning_content.CACHE_SECONDS = old_cache_seconds
        learning_content._cache = old_cache
        learning_content._expires_at = old_expiry
        learning_content._refreshing = old_refreshing


if __name__ == "__main__":
    run()
