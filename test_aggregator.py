#!/usr/bin/env python3
"""
Локальные проверки AI News Aggregator без сети, браузера и боевого Telegram.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import requests

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.db import NewsDatabase, group_runs_by_iso_week
from utils.filters import NewsFilter, build_run_ready_notification


class KeywordStatusTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self._tmp.name, "test.db")
        self.db = NewsDatabase(self.db_path)

    def tearDown(self):
        self.db.close()
        self._tmp.cleanup()

    def test_proposed_not_in_active_search_list(self):
        self.db.add_keyword("unique proposed phrase xyz", "proposed", run_id=None)
        active = [p.lower() for p in self.db.get_active_keywords()]
        self.assertNotIn("unique proposed phrase xyz", active)

    def test_accept_makes_active(self):
        kid = self.db.add_keyword("brand new tool phrase", "proposed")
        self.assertIsNotNone(kid)
        self.db.set_keyword_status(kid, "active")
        active = [p.lower() for p in self.db.get_active_keywords()]
        self.assertIn("brand new tool phrase", active)

    def test_reject_blocks_repropose(self):
        run_id = self.db.create_run(7)
        kid = self.db.add_keyword("noisy hype phrase", "proposed", run_id=run_id)
        self.db.set_keyword_status(kid, "rejected")
        added = self.db.propose_keywords(["Noisy Hype Phrase", "another new one"], run_id=run_id)
        phrases = {r["phrase"].lower() for r in self.db.get_keywords("proposed")}
        self.assertNotIn("noisy hype phrase", phrases)
        self.assertIn("another new one", phrases)
        self.assertEqual(added, 1)


class RedditOnlineAiFilterTests(unittest.TestCase):
    def setUp(self):
        self.filter = NewsFilter(
            [
                "AI automation",
                "AI agents",
                "ИИ для бизнеса",
            ]
        )

    def test_online_ai_business_passes(self):
        post = {
            "title": "How I automated my SaaS onboarding with AI agents",
            "description": "Online micro-SaaS, no office, pure digital workflow.",
            "source": "Reddit r/indiehackers",
        }
        self.assertTrue(self.filter.is_online_ai_business_post(post))

    def test_offline_business_fails(self):
        post = {
            "title": "Opened a brick and mortar coffee shop with AI menu boards",
            "description": "Local shop downtown.",
            "source": "Reddit r/Entrepreneur",
        }
        self.assertFalse(self.filter.is_online_ai_business_post(post))

    def test_business_without_ai_fails(self):
        post = {
            "title": "My journey launching an online subscription box",
            "description": "Marketing and shipping tips, no tech.",
            "source": "Reddit r/SideProject",
        }
        self.assertFalse(self.filter.is_online_ai_business_post(post))


class WeekGroupingTests(unittest.TestCase):
    def test_iso_weeks_newest_first(self):
        runs = [
            {
                "id": 1,
                "started_at": "2026-09-01T10:00:00+00:00",
                "status": "ok",
            },
            {
                "id": 2,
                "started_at": "2026-09-28T12:00:00+00:00",
                "status": "ok",
            },
            {
                "id": 3,
                "started_at": "2026-09-29T09:00:00+00:00",
                "status": "ok",
            },
        ]
        weeks = group_runs_by_iso_week(runs)
        self.assertGreaterEqual(len(weeks), 2)
        self.assertGreater(
            (weeks[0]["year"], weeks[0]["week"]),
            (weeks[-1]["year"], weeks[-1]["week"]),
        )
        # Самый новый прогон внутри верхней недели — выше
        top_ids = [r["id"] for r in weeks[0]["runs"]]
        self.assertEqual(top_ids[0], 3)


class TelegramNotificationTests(unittest.TestCase):
    def test_single_message_with_site_no_news_list(self):
        text = build_run_ready_notification("http://127.0.0.1:5050")
        self.assertIn("http://127.0.0.1:5050", text)
        self.assertIn("готов", text.lower())
        self.assertNotIn("Источники:", text)
        self.assertNotIn("Найдено новостей", text)
        self.assertNotIn("http://example.com/news", text)
        # Одно логическое сообщение (не список материалов)
        self.assertEqual(text.count("http://127.0.0.1:5050"), 1)


class EmptyRunSkipTests(unittest.TestCase):
    """Пустой прогон не пишет runs и не шлёт Telegram."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self._tmp.name, "test.db")
        self.db = NewsDatabase(self.db_path)

    def tearDown(self):
        self.db.close()
        self._tmp.cleanup()

    def test_empty_after_filters_skips_db_deepseek_telegram(self):
        from main import AINewsAggregator

        agg = AINewsAggregator.__new__(AINewsAggregator)
        agg.config = MagicMock()
        agg.config.NEWS_LOOKBACK_DAYS = 7
        agg.config.validate_config = MagicMock()
        agg.db = self.db
        agg.logger = MagicMock()
        agg.telegram_sender = MagicMock()
        agg.collect_news = MagicMock(return_value=([], ["Google News: отключён в .env"]))
        agg.process_news = MagicMock(return_value=[])
        agg._send_success_notification = MagicMock()

        with patch("main.DeepSeekClient") as ds_cls:
            agg.run()
            ds_cls.assert_not_called()

        self.assertEqual(self.db.list_runs(), [])
        agg._send_success_notification.assert_not_called()
        agg.telegram_sender.send_message.assert_not_called()

    def test_delete_runs_without_items_keeps_runs_with_items(self):
        empty_id = self.db.create_run(7)
        kept_id = self.db.create_run(7)
        self.db.save_items(
            kept_id,
            [
                {
                    "title": "AI agents for SaaS",
                    "url": "https://example.com/a",
                    "source": "test",
                    "description": "practice",
                    "ranking_score": 50,
                }
            ],
        )
        self.db.save_summary(empty_id, "should be removed with empty run")
        removed = self.db.delete_runs_without_items()
        self.assertEqual(removed, [empty_id])
        self.assertIsNone(self.db.get_run(empty_id))
        self.assertIsNone(self.db.get_summary(empty_id))
        kept = self.db.get_run(kept_id)
        self.assertIsNotNone(kept)
        self.assertEqual(kept["id"], kept_id)
        row = self.db._conn.execute(
            "SELECT COUNT(*) AS c FROM items WHERE run_id = ?", (kept_id,)
        ).fetchone()
        self.assertEqual(row["c"], 1)

    def test_nonempty_run_creates_row_and_notifies(self):
        from main import AINewsAggregator

        item = {
            "title": "Useful AI automation case",
            "url": "https://example.com/case",
            "source": "test",
            "description": "How AI agents helped online business",
            "ranking_score": 80,
            "published_date": datetime.now(timezone.utc),
        }
        agg = AINewsAggregator.__new__(AINewsAggregator)
        agg.config = MagicMock()
        agg.config.NEWS_LOOKBACK_DAYS = 7
        agg.config.validate_config = MagicMock()
        agg.db = self.db
        agg.logger = MagicMock()
        agg.collect_news = MagicMock(return_value=([item], []))
        agg.process_news = MagicMock(return_value=[item])
        agg._send_success_notification = MagicMock()

        fake_client = MagicMock()
        fake_client.build_weekly_analysis.return_value = "Разбор недели"
        fake_client.build_articles_and_keywords.return_value = (
            [
                {
                    "title": "Статья",
                    "body": "Текст",
                    "rationale": "почему",
                    "source_urls": ["https://example.com/case"],
                }
            ],
            ["new phrase"],
        )

        with patch("main.DeepSeekClient", return_value=fake_client):
            agg.run()

        runs = self.db.list_runs()
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["status"], "ok")
        self.assertEqual(self.db.get_summary(runs[0]["id"]), "Разбор недели")
        articles = self.db.get_articles_for_run(runs[0]["id"])
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["source_urls"], ["https://example.com/case"])
        agg._send_success_notification.assert_called_once_with(runs[0]["id"])


class ArticleSourceUrlsTests(unittest.TestCase):
    """source_urls у статей: БД, парсинг DeepSeek, API."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self._tmp.name, "test.db")
        self.db = NewsDatabase(self.db_path)

    def tearDown(self):
        self.db.close()
        self._tmp.cleanup()

    def test_save_and_get_article_source_urls(self):
        run_id = self.db.create_run(7)
        self.db.save_articles(
            run_id,
            [
                {
                    "title": "Тема",
                    "body": "Текст статьи",
                    "rationale": "зачем",
                    "source_urls": [
                        "https://example.com/a",
                        "https://example.com/b",
                    ],
                }
            ],
        )
        articles = self.db.get_articles_for_run(run_id)
        self.assertEqual(
            articles[0]["source_urls"],
            ["https://example.com/a", "https://example.com/b"],
        )
        one = self.db.get_article(articles[0]["id"])
        self.assertEqual(one["source_urls"], articles[0]["source_urls"])

    def test_parse_keeps_only_allowed_item_urls(self):
        from utils.deepseek import _parse_articles_payload

        raw = (
            '{"articles":[{"title":"Т","body":"Б","rationale":"",'
            '"source_urls":["https://ok.example/x","https://fake.example/y"]}],'
            '"keywords":[]}'
        )
        articles, _ = _parse_articles_payload(
            raw,
            max_articles=5,
            allowed_urls=["https://ok.example/x"],
        )
        self.assertEqual(articles[0]["source_urls"], ["https://ok.example/x"])

    def test_api_article_returns_source_urls(self):
        import web as web_mod

        run_id = self.db.create_run(7)
        self.db.save_articles(
            run_id,
            [
                {
                    "title": "API статья",
                    "body": "Тело",
                    "rationale": "",
                    "source_urls": ["https://example.com/src"],
                }
            ],
        )
        article_id = self.db.get_articles_for_run(run_id)[0]["id"]
        orig = web_mod.get_db
        web_mod.get_db = lambda: self.db
        try:
            client = web_mod.app.test_client()
            resp = client.get(f"/api/articles/{article_id}")
            run_resp = client.get(f"/api/runs/{run_id}")
        finally:
            web_mod.get_db = orig
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp.get_json()["article"]["source_urls"],
            ["https://example.com/src"],
        )
        self.assertEqual(
            run_resp.get_json()["articles"][0]["source_urls"],
            ["https://example.com/src"],
        )


class SslTrustTests(unittest.TestCase):
    def test_use_system_certificates_calls_truststore_inject(self):
        from unittest.mock import MagicMock, patch

        from utils.ssl_trust import use_system_certificates

        fake_truststore = MagicMock()
        with patch.dict(sys.modules, {"truststore": fake_truststore}):
            use_system_certificates()
        fake_truststore.inject_into_ssl.assert_called_once_with()


class HackerNewsConnectionTests(unittest.TestCase):
    def test_firebase_connection_error_skips_story_fetches(self):
        from sources.hackernews_parser import HackerNewsParser

        session = MagicMock()
        calls = []

        def fake_get(url, **kwargs):
            calls.append(url)
            if "topstories.json" in url or "beststories.json" in url:
                raise requests.ConnectionError("network unreachable")
            if "algolia" in url:
                resp = MagicMock()
                resp.raise_for_status = MagicMock()
                resp.json.return_value = {"hits": []}
                return resp
            self.fail(f"неожиданный запрос истории: {url}")

        session.get.side_effect = fake_get

        with patch("sources.hackernews_parser.requests.Session", return_value=session):
            with patch("sources.hackernews_parser.time.sleep"):
                parser = HackerNewsParser(active_keywords=["artificial intelligence"])
                result = parser.search_stories(max_results=5)

        self.assertEqual(result, [])
        self.assertTrue(any("topstories.json" in u for u in calls))
        self.assertFalse(any("/item/" in u for u in calls))

    def test_algolia_connection_error_stops_remaining_keywords(self):
        from sources.hackernews_parser import HackerNewsParser

        session = MagicMock()
        algolia_calls = []

        def fake_get(url, **kwargs):
            if "topstories.json" in url or "beststories.json" in url:
                resp = MagicMock()
                resp.raise_for_status = MagicMock()
                resp.json.return_value = []
                return resp
            if "algolia" in url:
                algolia_calls.append(url)
                raise requests.ConnectionError("local ports exhausted")
            self.fail(f"неожиданный URL: {url}")

        session.get.side_effect = fake_get

        with patch("sources.hackernews_parser.requests.Session", return_value=session):
            with patch("sources.hackernews_parser.time.sleep"):
                parser = HackerNewsParser(
                    active_keywords=["alpha keyword", "beta keyword", "gamma keyword"]
                )
                result = parser.search_stories(max_results=5)

        self.assertEqual(result, [])
        self.assertEqual(len(algolia_calls), 1)


class KeywordDeleteFetchTests(unittest.TestCase):
    """Fetch-POST ключевых слов: JSON ok/ошибка, без redirect, без data/news.db."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self._tmp.name, "test.db")
        self.db = NewsDatabase(self.db_path)
        import web as web_mod

        self.web_mod = web_mod
        self._orig_get_db = web_mod.get_db
        web_mod.get_db = lambda: self.db
        self.client = web_mod.app.test_client()

    def tearDown(self):
        self.web_mod.get_db = self._orig_get_db
        self.db.close()
        self._tmp.cleanup()

    def _fetch_post(self, data):
        return self.client.post(
            "/keywords",
            data=data,
            headers={"X-Requested-With": "fetch"},
        )

    def _assert_json_ok_no_redirect(self, resp, expected):
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(resp.status_code, range(300, 400))
        self.assertIsNone(resp.headers.get("Location"))
        self.assertEqual(resp.get_json(), expected)

    def test_delete_with_fetch_header_returns_json_and_removes_phrase(self):
        kid = self.db.add_keyword("phrase to delete via fetch", "active")
        self.assertIsNotNone(kid)
        resp = self._fetch_post({"action": "delete", "id": str(kid)})
        self._assert_json_ok_no_redirect(resp, {"ok": True})
        phrases = {r["phrase"].lower() for r in self.db.get_keywords("active")}
        self.assertNotIn("phrase to delete via fetch", phrases)

    def test_add_with_fetch_header_returns_json_and_no_redirect(self):
        resp = self._fetch_post(
            {"action": "add_active", "phrase": "fresh fetch phrase"}
        )
        data = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.headers.get("Location"))
        self.assertTrue(data["ok"])
        self.assertEqual(data["phrase"], "fresh fetch phrase")
        self.assertIsInstance(data["id"], int)
        phrases = {r["phrase"].lower() for r in self.db.get_keywords("active")}
        self.assertIn("fresh fetch phrase", phrases)

    def test_edit_with_fetch_header_returns_json_and_no_redirect(self):
        kid = self.db.add_keyword("old edit phrase", "active")
        resp = self._fetch_post(
            {"action": "edit", "id": str(kid), "phrase": "new edit phrase"}
        )
        self._assert_json_ok_no_redirect(
            resp, {"ok": True, "id": kid, "phrase": "new edit phrase"}
        )
        phrases = {r["phrase"].lower() for r in self.db.get_keywords("active")}
        self.assertIn("new edit phrase", phrases)
        self.assertNotIn("old edit phrase", phrases)

    def test_accept_with_fetch_header_returns_json_and_no_redirect(self):
        kid = self.db.add_keyword("proposed accept phrase", "proposed")
        resp = self._fetch_post({"action": "accept", "id": str(kid)})
        self._assert_json_ok_no_redirect(
            resp, {"ok": True, "id": kid, "phrase": "proposed accept phrase"}
        )
        active = {r["phrase"].lower() for r in self.db.get_keywords("active")}
        proposed = {r["phrase"].lower() for r in self.db.get_keywords("proposed")}
        self.assertIn("proposed accept phrase", active)
        self.assertNotIn("proposed accept phrase", proposed)

    def test_reject_with_fetch_header_returns_json_and_no_redirect(self):
        kid = self.db.add_keyword("proposed reject phrase", "proposed")
        resp = self._fetch_post({"action": "reject", "id": str(kid)})
        self._assert_json_ok_no_redirect(
            resp, {"ok": True, "id": kid, "phrase": "proposed reject phrase"}
        )
        rejected = {r["phrase"].lower() for r in self.db.get_keywords("rejected")}
        proposed = {r["phrase"].lower() for r in self.db.get_keywords("proposed")}
        self.assertIn("proposed reject phrase", rejected)
        self.assertNotIn("proposed reject phrase", proposed)

    def test_duplicate_add_with_fetch_returns_json_400(self):
        self.db.add_keyword("dup fetch phrase", "active")
        resp = self._fetch_post(
            {"action": "add_active", "phrase": "dup fetch phrase"}
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIsNone(resp.headers.get("Location"))
        data = resp.get_json()
        self.assertIsNotNone(data)
        self.assertFalse(data["ok"])
        self.assertIn("error", data)
        self.assertNotIn("text/html", (resp.content_type or "").lower())

    def test_keywords_template_shows_save_toast_on_successful_edit(self):
        """В Vue-компоненте ключевых слов тост только при успешном edit; фраза — текст."""
        src_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "frontend",
            "src",
            "views",
            "KeywordsView.vue",
        )
        with open(src_path, encoding="utf-8") as f:
            src = f.read()
        self.assertIn("showSaveToast", src)
        self.assertIn('action === "edit"', src)
        self.assertRegex(
            src,
            r'if\s*\(\s*action\s*===\s*"edit"\s*\)\s*\{[^}]*showSaveToast',
        )
        self.assertEqual(src.count("showSaveToast("), 2)
        self.assertNotIn("form.submit()", src)
        self.assertNotIn("v-html", src)
        self.assertNotIn("window.location", src)
        self.assertIn("is-busy", src)
        self.assertRegex(src, r"Фраза сохранена:\s*\{\{\s*toastPhrase\s*\}\}")


class ManualRunTests(unittest.TestCase):
    """Свои тексты: тот же разбор, без сети и без боевого Telegram."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self._tmp.name, "test.db")
        self.db = NewsDatabase(self.db_path)
        import web as web_mod

        self.web_mod = web_mod
        self._orig_get_db = web_mod.get_db
        web_mod.get_db = lambda: self.db
        self.client = web_mod.app.test_client()
        self._validate = patch("main.Config.validate_config", return_value=True)
        self.validate_mock = self._validate.start()

    def tearDown(self):
        self._validate.stop()
        self.web_mod.get_db = self._orig_get_db
        self.db.close()
        self._tmp.cleanup()

    def _fake_deepseek(self):
        fake = MagicMock()
        fake.build_weekly_analysis.return_value = "Разбор недели"
        fake.build_articles_and_keywords.return_value = (
            [{"title": "Статья", "body": "Текст", "rationale": "почему"}],
            ["новая фраза ручного прогона"],
        )
        return fake

    def test_two_russian_texts_without_keywords_reach_model(self):
        from utils.filters import NewsFilter

        pairs = [
            {
                "title": "Заметки о дачном саде",
                "text": "Поливал грядки и собирал яблоки всё лето",
            },
            {
                "title": "Как прошла обычная неделя",
                "text": "Гулял по району и читал бумажную книгу",
            },
        ]
        score = NewsFilter([]).calculate_relevance_score
        for pair in pairs:
            self.assertLess(score(pair["title"], pair["text"]), 20)

        fake = self._fake_deepseek()
        with patch("main.DeepSeekClient", return_value=fake), patch(
            "main.TelegramSender"
        ) as tg, patch.object(
            __import__("main").AINewsAggregator, "collect_news"
        ) as collect:
            tg.return_value.send_message.return_value = True
            resp = self.client.post("/api/manual-run", json={"items": pairs})
            collect.assert_not_called()

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["ok"])
        run_id = data["run_id"]
        self.assertIsInstance(run_id, int)

        runs = self.db.list_runs()
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["id"], run_id)
        self.assertEqual(runs[0]["status"], "ok")

        rows = self.db._conn.execute(
            "SELECT source, title, url, text FROM items WHERE run_id = ? ORDER BY id",
            (run_id,),
        ).fetchall()
        self.assertEqual(len(rows), 2)
        self.assertEqual({row["title"] for row in rows}, {p["title"] for p in pairs})
        self.assertEqual({row["text"] for row in rows}, {p["text"] for p in pairs})
        self.assertTrue(all(row["source"] == "Вручную" for row in rows))
        self.assertTrue(all((row["url"] or "") == "" for row in rows))

        passed = fake.build_weekly_analysis.call_args[0][0]
        self.assertEqual(len(passed), 2)
        self.assertEqual(
            {item.get("description") for item in passed},
            {p["text"] for p in pairs},
        )
        self.assertEqual(self.db.get_summary(run_id), "Разбор недели")
        self.assertEqual(len(self.db.get_articles_for_run(run_id)), 1)
        self.assertEqual(tg.return_value.send_message.call_count, 1)
        self.validate_mock.assert_called()

    def test_manual_item_url_saved_from_url_or_link(self):
        fake = self._fake_deepseek()
        with patch("main.DeepSeekClient", return_value=fake), patch(
            "main.TelegramSender"
        ) as tg:
            tg.return_value.send_message.return_value = True
            resp = self.client.post(
                "/api/manual-run",
                json={
                    "items": [
                        {
                            "title": "Опыт с агентами в сервисе",
                            "text": "Текст с источником",
                            "url": "https://example.com/manual-a",
                        },
                        {
                            "title": "Домашний сад осенью",
                            "text": "Другой текст про яблоки",
                            "link": "https://example.com/manual-b",
                        },
                        {
                            "title": "Прогулка по району",
                            "text": "Только текст без адреса",
                        },
                    ]
                },
            )
        self.assertEqual(resp.status_code, 200)
        run_id = resp.get_json()["run_id"]
        rows = self.db._conn.execute(
            "SELECT title, url FROM items WHERE run_id = ? ORDER BY id",
            (run_id,),
        ).fetchall()
        by_title = {row["title"]: row["url"] or "" for row in rows}
        self.assertEqual(len(rows), 3)
        self.assertEqual(
            by_title["Опыт с агентами в сервисе"], "https://example.com/manual-a"
        )
        self.assertEqual(by_title["Домашний сад осенью"], "https://example.com/manual-b")
        self.assertEqual(by_title["Прогулка по району"], "")
        passed = fake.build_weekly_analysis.call_args[0][0]
        passed_urls = {item.get("url") or "" for item in passed}
        self.assertEqual(
            passed_urls,
            {
                "https://example.com/manual-a",
                "https://example.com/manual-b",
                "",
            },
        )

    def test_title_with_quotes_and_dash_is_not_dropped(self):
        title = "«Неделя» — заметка о жизни"
        text = "Короткий рассказ о домашних делах"
        lang = NewsFilter([])
        self.assertFalse(lang.is_english_or_russian(title))
        self.assertTrue(lang.title_letters_are_ru_or_en(title))

        fake = self._fake_deepseek()
        with patch("main.DeepSeekClient", return_value=fake), patch(
            "main.TelegramSender"
        ) as tg:
            tg.return_value.send_message.return_value = True
            resp = self.client.post(
                "/api/manual-run",
                json={"items": [{"title": title, "text": text}]},
            )

        self.assertEqual(resp.status_code, 200)
        run_id = resp.get_json()["run_id"]
        passed = fake.build_weekly_analysis.call_args[0][0]
        self.assertEqual([item["title"] for item in passed], [title])
        row = self.db._conn.execute(
            "SELECT title, text FROM items WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        self.assertEqual(row["title"], title)
        self.assertEqual(row["text"], text)

    def test_empty_list_and_foreign_title_return_400_without_run(self):
        foreign = {"items": [{"title": "你好世界今天", "text": "Просто заметка"}]}
        cases = [
            ("empty-list", {"items": []}),
            ("not-a-list", {"items": {"title": "Заголовок", "text": "Текст"}}),
            ("blank-pair", {"items": [{"title": "  ", "text": "  "}]}),
            ("foreign-title", foreign),
        ]
        for name, payload in cases:
            with self.subTest(name=name):
                with patch("main.DeepSeekClient") as ds, patch(
                    "main.TelegramSender"
                ) as tg:
                    resp = self.client.post("/api/manual-run", json=payload)
                    ds.assert_not_called()
                    tg.return_value.send_message.assert_not_called()
                self.assertEqual(resp.status_code, 400)
                data = resp.get_json()
                self.assertFalse(data["ok"])
                self.assertTrue(data.get("error"))
                if name == "foreign-title":
                    self.assertIn("русском", data["error"])
                else:
                    self.assertIn("пара", data["error"])
                self.assertEqual(self.db.list_runs(), [])

        with self.subTest(name="empty-body"):
            with patch("main.DeepSeekClient") as ds, patch("main.TelegramSender"):
                resp = self.client.post(
                    "/api/manual-run",
                    data=b"",
                    content_type="application/json",
                )
                ds.assert_not_called()
            self.assertEqual(resp.status_code, 400)
            self.assertFalse(resp.get_json()["ok"])
            self.assertEqual(self.db.list_runs(), [])

    def test_process_news_still_drops_low_relevance(self):
        from main import AINewsAggregator

        agg = AINewsAggregator(db=self.db)
        item = {
            "title": "Погода на неделе в городе",
            "description": "Будет дождь и ветер на улице",
            "url": "https://example.com/weather-week",
            "source": "Городской сайт",
            "published_date": datetime.now(timezone.utc),
        }
        self.assertTrue(agg.filter.is_english_or_russian(item["title"]))
        self.assertLess(
            agg.filter.calculate_relevance_score(item["title"], item["description"]),
            20,
        )
        self.assertEqual(agg.process_news([item]), [])

        manual = agg.process_manual_items(
            [
                {
                    "title": item["title"],
                    "description": item["description"],
                    "url": "",
                    "source": "Вручную",
                    "published_date": item["published_date"],
                }
            ]
        )
        self.assertEqual(len(manual), 1)
        self.assertEqual(manual[0]["title"], item["title"])

    def test_deepseek_failure_marks_failed_and_skips_telegram(self):
        fake = self._fake_deepseek()
        fake.build_weekly_analysis.side_effect = RuntimeError("модель недоступна")
        with patch("main.DeepSeekClient", return_value=fake), patch(
            "main.TelegramSender"
        ) as tg:
            tg.return_value.send_message.return_value = True
            resp = self.client.post(
                "/api/manual-run",
                json={
                    "items": [
                        {
                            "title": "Обычная заметка про сад",
                            "text": "Поливал цветы утром",
                        }
                    ]
                },
            )
        self.assertEqual(resp.status_code, 500)
        data = resp.get_json()
        self.assertFalse(data["ok"])
        self.assertIn("модель недоступна", data["error"])
        runs = self.db.list_runs()
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["status"], "failed")
        tg.return_value.send_message.assert_not_called()

    def test_manual_panel_source_has_no_v_html(self):
        src_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "frontend",
            "src",
            "App.vue",
        )
        with open(src_path, encoding="utf-8") as f:
            src = f.read()
        self.assertIn("Свои тексты", src)
        self.assertIn("Ещё", src)
        self.assertIn("Убрать", src)
        self.assertIn(">Ок<", src)
        self.assertIn("Идёт разбор…", src)
        self.assertIn("is-busy", src)
        self.assertIn("/api/manual-run", src)
        self.assertIn("Ссылка", src)
        self.assertIn("pair.url", src)
        self.assertNotIn("v-html", src)

    def test_article_view_shows_source_urls_block(self):
        src_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "frontend",
            "src",
            "views",
            "ArticleView.vue",
        )
        with open(src_path, encoding="utf-8") as f:
            src = f.read()
        self.assertIn("Использованные ссылки", src)
        self.assertIn("source_urls", src)
        self.assertIn("sourceUrls", src)


def main():

    print("Локальные тесты AI News Aggregator (без сети / Telegram / браузера)")
    print("=" * 60)
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
