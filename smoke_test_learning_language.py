"""Offline regression tests for Japanese-only RSS, fallback and cache output."""
from __future__ import annotations

import copy
import time
import unittest
from unittest.mock import patch
from xml.sax.saxutils import escape

import learning_content as learning


JA_TITLE = "ICMの基本を学ぶ"
JA_BODY = "トーナメントでのリスクと報酬を考え、ポーカーの戦略を日本語で解説します。"
URL = "https://japan.gtowizard.com/blog/icm-basics/"


def item(title=JA_TITLE, description=JA_BODY, body=None, url=URL, language="", date=""):
    content = f"<content:encoded>{escape(body)}</content:encoded>" if body is not None else ""
    return (f'<item {language}><title>{escape(title)}</title><link>{escape(url)}</link>'
            f'<description>{escape(description)}</description>{content}'
            f'<pubDate>{escape(date)}</pubDate></item>')


def feed(*items, language="ja"):
    return (f'<rss xmlns:content="http://purl.org/rss/1.0/modules/content/" '
            f'xmlns:dc="http://purl.org/dc/elements/1.1/"><channel>'
            f'<language>{language}</language>{"".join(items)}</channel></rss>').encode()


class JapaneseArticlesTest(unittest.TestCase):
    def test_japanese_with_poker_terms_and_old_dates(self):
        for title in (JA_TITLE, "GTO Wizardになる方法", "SPRとポストフロップ", "EVとは", "ﾎﾟｰｶｰの基本"):
            with self.subTest(title=title):
                articles = learning._parse_gtowizard_articles(feed(item(title=title, date="Tue, 05 Dec 2023 00:00:00 +0900")))
                self.assertEqual(len(articles), 1)
                self.assertEqual(articles[0]["language"], "ja")
                self.assertTrue(articles[0]["published_at"].startswith("2023-12-05"))

    def test_english_and_ambiguous_titles_are_not_japanese(self):
        for title in ("Understanding ICM", "Poker strategy ー", "Advanced Poker Strategy 日本語", "扑克策略基础", "あ"):
            with self.subTest(title=title):
                self.assertEqual(learning._parse_gtowizard_articles(feed(item(title=title))), [])

    def test_title_does_not_override_english_or_missing_body(self):
        for description, body in (
            ("English poker strategy explanation.", None),
            ("", "English poker strategy explanation."),
            (JA_BODY, "English poker strategy explanation."),
            ("", None),
            ("", "<script>日本語の解説</script>English poker strategy explanation."),
        ):
            with self.subTest(description=description, body=body):
                self.assertEqual(learning._parse_gtowizard_articles(feed(item(description=description, body=body))), [])

    def test_wordpress_full_content_and_empty_description(self):
        body = '<style>.english-class { color: red; }</style><h1>ICM</h1><p>' + JA_BODY + '</p>'
        articles = learning._parse_gtowizard_articles(feed(item(description="", body=body)))
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["summary"], "")

    def test_explicit_non_japanese_languages_are_rejected(self):
        for language in ('xml:lang="en"', 'xml:lang="zh-CN"'):
            self.assertEqual(learning._parse_gtowizard_articles(feed(item(language=language))), [])
        self.assertEqual(learning._parse_gtowizard_articles(feed(item(), language="en-US")), [])
        with_dc = item().replace('</item>', '<dc:language>en</dc:language></item>')
        self.assertEqual(learning._parse_gtowizard_articles(feed(with_dc)), [])
        self.assertEqual(len(learning._parse_gtowizard_articles(feed(item(language='xml:lang="ja-JP"')))), 1)
        self.assertEqual(len(learning._parse_gtowizard_articles(feed(item(), language=""))), 1)

    def test_only_direct_official_japanese_article_urls(self):
        for url in (
            'https://blog.gtowizard.com/icm-basics/',
            'https://japan.gtowizard.com.evil.example/blog/icm/',
            'http://japan.gtowizard.com/blog/icm/',
            'https://user:password@japan.gtowizard.com/blog/icm/',
            'https://japan.gtowizard.com:invalid/blog/icm/',
            'https://japan.gtowizard.com:8443/blog/icm/',
            URL + '?lang=en',
            'https://japan.gtowizard.com/blog/news/product/',
            'https://japan.gtowizard.com/blog/videos/',
            'https://japan.gtowizard.com/blog/',
            'https://japan.gtowizard.com/blog/%2e%2e/',
            'https://japan.gtowizard.com/blog/../english/',
            'https://japan.gtowizard.com/blog/\\english/',
        ):
            with self.subTest(url=url):
                self.assertEqual(learning._parse_gtowizard_articles(feed(item(url=url))), [])

    def test_mixed_feed_deduplicates_after_filtering(self):
        raw = feed(item(title="English", url=URL), item(), item(url=URL+'#section'),
                   item(url=URL.replace('icm-basics', 'older'), date='Tue, 05 Dec 2023 00:00:00 +0900'))
        result = learning._parse_gtowizard_articles(raw)
        self.assertEqual(len(result), 2)
        self.assertEqual({x['title'] for x in result}, {JA_TITLE})

    def test_fallback_does_not_trust_label_or_host_alone(self):
        good = dict(learning.ARTICLE_FALLBACK[-1])
        bad = [dict(good, title="English article"), dict(good, language="en"),
               dict(good, summary="Read this English strategy guide."),
               dict(good, url="https://blog.gtowizard.com/english/"), None]
        with patch.object(learning, 'ARTICLE_FALLBACK', tuple(bad+[good])):
            self.assertEqual(learning._fallback_payload()['articles'], [good])

    def test_empty_english_invalid_and_unavailable_feeds_use_reviewed_fallback(self):
        expected = learning._fallback_payload()['articles']
        for value in (feed(), feed(item(title="English")), b'<broken', TimeoutError("offline"), ValueError("too large")):
            with self.subTest(value=type(value).__name__):
                kwargs = {'side_effect': value} if isinstance(value, Exception) else {'return_value': value}
                with patch.object(learning, '_fetch_bytes', **kwargs):
                    payload = learning._refresh_payload()
                self.assertEqual(payload['articles'], expected)
                self.assertEqual(payload['policy']['articles'], 'ja-only')
                self.assertTrue(payload['videos'])

    def test_live_articles_precede_fallback_without_age_cutoff(self):
        with patch.object(learning, '_fetch_bytes', return_value=feed(item(date='Tue, 05 Dec 2023 00:00:00 +0900'))):
            payload = learning._refresh_payload()
        self.assertEqual(payload['articles'][0]['url'], URL)
        self.assertTrue(payload['articles'][0]['published_at'].startswith('2023'))
        self.assertLessEqual(len(payload['articles']), 6)

    def test_cached_english_removed_for_both_fresh_and_stale_reads(self):
        base = learning._fallback_payload()
        poisoned = copy.deepcopy(base)
        poisoned['articles'].insert(0, dict(base['articles'][0], title='English strategy guide'))
        poisoned['policy']['articles'] = 'ja-first'
        for expiry, refreshing, expected_starts in ((time.monotonic()+3600, False, 0), (0, False, 1), (0, True, 0)):
            with self.subTest(expiry=expiry, refreshing=refreshing):
                with patch.object(learning, '_cache', poisoned), patch.object(learning, '_expires_at', expiry), \
                     patch.object(learning, '_refreshing', refreshing), patch.object(learning.threading, 'Thread') as thread:
                    payload = learning.get_learning_content()
                    self.assertEqual(payload['articles'], base['articles'])
                    self.assertEqual(payload['policy']['articles'], 'ja-only')
                    self.assertEqual(thread.call_count, expected_starts)
                    payload['articles'][0]['title'] = 'caller mutation'
                    self.assertEqual(poisoned['articles'][1]['title'], base['articles'][0]['title'])

    def test_cold_start_and_worker_keep_validated_fallback(self):
        with patch.object(learning, '_cache', {}), patch.object(learning, '_expires_at', 0), \
             patch.object(learning, '_refreshing', False), patch.object(learning.threading, 'Thread'):
            self.assertEqual(learning.get_learning_content()['articles'], learning._fallback_payload()['articles'])
        with patch.object(learning, '_cache', {}), patch.object(learning, '_expires_at', 0), \
             patch.object(learning, '_refreshing', True), patch.object(learning, '_fetch_bytes', side_effect=TimeoutError):
            learning._refresh_worker()
            self.assertFalse(learning._refreshing)
            self.assertGreater(learning._expires_at, time.monotonic())
            self.assertEqual(learning._cache['articles'], learning._fallback_payload()['articles'])


def run():
    result = unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(JapaneseArticlesTest))
    if not result.wasSuccessful():
        raise AssertionError('Japanese-only article regression failed')
    print('JJ_LEARNING_LANGUAGE_SMOKE_OK')


if __name__ == '__main__':
    run()
