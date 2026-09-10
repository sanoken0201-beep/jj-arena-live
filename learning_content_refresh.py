from __future__ import annotations


# Verified Japanese GTO Wizard Japan articles current as of 2026-09-10.
# The live RSS feed remains authoritative; these are the immediate fallback
# shown while the first background refresh is running or if the feed is down.
LATEST_JA_ARTICLES = (
    {
        "title": "プロファイル別エクスプロイト 第3回｜マニアック",
        "url": "https://japan.gtowizard.com/blog/exploiting-profiles-episode-iii-the-maniac/",
        "source": "GTO Wizard Japan",
        "language": "ja",
        "published_at": "2026-08-30T00:00:00+09:00",
        "topic": "エクスプロイト",
        "summary": "アグレッシブすぎるManiac型の傾向をモデル化し、どのように戦略を調整するかを考える日本語記事です。",
    },
    {
        "title": "IPでドローをベットする本当の基準",
        "url": "https://japan.gtowizard.com/blog/betting-draws-in-position-the-real-rules/",
        "source": "GTO Wizard Japan",
        "language": "ja",
        "published_at": "2026-08-30T00:00:00+09:00",
        "topic": "ポストフロップ / ドロー",
        "summary": "ドローを自動的にブラフへ回すのではなく、レンジ全体と将来ストリートまで含めてベット判断を整理する記事です。",
    },
    {
        "title": "リンプポットをどうプレイするか",
        "url": "https://japan.gtowizard.com/blog/is-limping-pimping/",
        "source": "GTO Wizard Japan",
        "language": "ja",
        "published_at": "2026-08-22T00:00:00+09:00",
        "topic": "エクスプロイト / 理論",
        "summary": "リンプを含むポットで、通常のレイズポットとは異なるレンジと戦略の考え方を整理する日本語記事です。",
    },
    {
        "title": "バブルとFTバブルの違い",
        "url": "https://japan.gtowizard.com/blog/money-bubble-vs-final-table-bubble/",
        "source": "GTO Wizard Japan",
        "language": "ja",
        "published_at": "2026-08-09T00:00:00+09:00",
        "topic": "ICM / トーナメント",
        "summary": "通常のマネーバブルとファイナルテーブル・バブルで、ICM圧力と戦略がどう変わるかを扱います。",
    },
    {
        "title": "なぜ自分のソリューションはGTO Wizardと違うのか？",
        "url": "https://japan.gtowizard.com/blog/why-doesnt-my-solution-match-gto-wizard/",
        "source": "GTO Wizard Japan",
        "language": "ja",
        "published_at": "2026-08-09T00:00:00+09:00",
        "topic": "GTO / ソルバー",
        "summary": "プリフロップレンジ、ベットサイズ、レーキ、SPRなどの条件差でソルバー出力が変わる理由を確認できます。",
    },
    {
        "title": "ペアボードでBBのチェックレイズにどう対応するか",
        "url": "https://japan.gtowizard.com/blog/defending-vs-bb-check-raise-on-paired-flops/",
        "source": "GTO Wizard Japan",
        "language": "ja",
        "published_at": "2026-08-04T00:00:00+09:00",
        "topic": "トーナメント / ポストフロップ",
        "summary": "ペアボードでBBからチェックレイズされた際のコール・3ベット・フォールド構成を考える日本語記事です。",
    },
)


def apply(module) -> None:
    """Replace the stale article fallback and force a fresh feed cycle."""
    module.ARTICLE_FALLBACK = LATEST_JA_ARTICLES
    # A one-hour cache keeps the homepage fresh without making external RSS
    # availability part of normal page latency (stale-while-revalidate remains).
    module.CACHE_SECONDS = 60 * 60
    with module._cache_lock:
        module._cache = {}
        module._expires_at = 0.0
        module._refreshing = False
