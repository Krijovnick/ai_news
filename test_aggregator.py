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

    def test_plan_ignores_unknown_and_reused_item_ids(self):
        from utils.deepseek import _parse_plan_payload

        raw = (
            '{"topics":['
            '{"topic":"А","angle":"","why_together":"","item_ids":[1,2,99]},'
            '{"topic":"Б","angle":"","why_together":"","item_ids":[2]},'
            '{"topic":"В","angle":"","why_together":"","item_ids":["3"]}'
            '],"keywords":["фраза"]}'
        )
        topics, keywords = _parse_plan_payload(raw, item_count=3)
        self.assertEqual([t["topic"] for t in topics], ["А", "В"])
        self.assertEqual(topics[0]["item_indexes"], [0, 1])
        self.assertEqual(topics[1]["item_indexes"], [2])
        self.assertEqual(keywords, ["фраза"])

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


class DeepSeekPromptsTests(unittest.TestCase):
    """Единый YAML промптов: загрузка, плейсхолдеры; без файла/битый — ошибка."""

    def setUp(self):
        from utils.config import Config

        # По умолчанию без Search/Fetch: тесты не ходят в сеть; нужные тесты включают явно.
        self._web_patch = patch.object(Config, "DEEPSEEK_WEB_TOOLS", False)
        self._web_patch.start()

    def tearDown(self):
        from utils.deepseek import clear_prompts_cache

        self._web_patch.stop()
        clear_prompts_cache()

    def test_load_default_prompts_file(self):
        from utils.deepseek import clear_prompts_cache, load_author_prompt, load_prompts

        clear_prompts_cache()
        prompts = load_prompts()
        self.assertIn("weekly_analysis", prompts)
        self.assertIn("articles_and_keywords", prompts)
        self.assertIn("{materials}", prompts["weekly_analysis"]["user_single"])
        self.assertIn("{partials}", prompts["weekly_analysis"]["user_merge"])
        self.assertEqual(prompts["weekly_analysis"]["partials_joiner"], "\n\n---\n\n")
        author = load_author_prompt()
        self.assertIn("первого лица", author)
        self.assertIn("{author}", prompts["articles_and_keywords"]["write_user"])
        self.assertIn("{recent_titles}", prompts["articles_and_keywords"]["plan_user"])
        self.assertIn("{materials}", prompts["articles_and_keywords"]["write_user"])

    def test_missing_file_raises_and_logs(self):
        from utils.deepseek import PromptsLoadError, clear_prompts_cache, load_prompts

        clear_prompts_cache()
        missing = os.path.join(tempfile.gettempdir(), "ai_news_no_prompts.yaml")
        with self.assertLogs("utils.deepseek", level="ERROR") as cm:
            with self.assertRaises(PromptsLoadError) as ctx:
                load_prompts(missing)
        self.assertTrue(any("не найден" in m for m in cm.output))
        self.assertIn("не найден", str(ctx.exception))

    def test_invalid_yaml_raises_and_logs(self):
        from utils.deepseek import PromptsLoadError, clear_prompts_cache, load_prompts

        clear_prompts_cache()
        path = os.path.join(tempfile.gettempdir(), "ai_news_bad_prompts.yaml")
        with open(path, "w", encoding="utf-8") as f:
            f.write("weekly_analysis: [\n  broken")
        try:
            with self.assertLogs("utils.deepseek", level="ERROR") as cm:
                with self.assertRaises(PromptsLoadError):
                    load_prompts(path)
            self.assertTrue(any("Не удалось прочитать" in m for m in cm.output))
        finally:
            try:
                os.remove(path)
            except OSError:
                pass

    def test_incomplete_structure_raises(self):
        from utils.deepseek import PromptsLoadError, clear_prompts_cache, load_prompts

        clear_prompts_cache()
        path = os.path.join(tempfile.gettempdir(), "ai_news_incomplete_prompts.yaml")
        with open(path, "w", encoding="utf-8") as f:
            f.write("weekly_analysis:\n  system_single: only one key\n")
        try:
            with self.assertLogs("utils.deepseek", level="ERROR"):
                with self.assertRaises(PromptsLoadError) as ctx:
                    load_prompts(path)
            self.assertIn("невалидн", str(ctx.exception).lower())
        finally:
            try:
                os.remove(path)
            except OSError:
                pass

    def test_build_weekly_uses_templates(self):
        from utils.deepseek import DeepSeekClient, clear_prompts_cache

        clear_prompts_cache()
        client = DeepSeekClient(api_key="test-key")
        captured = []

        def fake_chat(messages, temperature=0.7):
            captured.append(messages)
            return "разбор"

        client._chat = fake_chat
        items = [
            {
                "title": "Тема",
                "source": "HN",
                "url": "https://example.com/1",
                "description": "Текст материала",
            }
        ]
        result = client.build_weekly_analysis(items)
        self.assertEqual(result, "разбор")
        self.assertEqual(len(captured), 1)
        user = captured[0][1]["content"]
        self.assertIn("подробный разбор недели", user)
        self.assertIn("https://example.com/1", user)
        self.assertIn("Тема", user)

    def test_articles_one_request_per_topic_with_own_materials(self):
        from utils.deepseek import DeepSeekClient, clear_prompts_cache

        clear_prompts_cache()
        client = DeepSeekClient(api_key="test-key")
        captured = []
        plan = (
            '{"topics":['
            '{"topic":"Агент удалил базу","angle":"права","why_together":"один инцидент","item_ids":[1,3]},'
            '{"topic":"Галлюцинация в поддержке","angle":"проверка","why_together":"","item_ids":[2]}'
            '],"keywords":["агентные права"]}'
        )

        def fake_chat(messages, temperature=0.7, max_tokens=None):
            captured.append(messages[1]["content"])
            if len(captured) == 1:
                return plan
            return '{"title":"Заголовок","body":"Текст","rationale":"важно"}'

        client._chat = fake_chat
        items = [
            {"title": "Агент стёр прод", "url": "https://a.example/1", "description": "x"},
            {"title": "Бот выдумал скидку", "url": "https://b.example/2", "description": "y"},
            {"title": "Ещё про стёртый прод", "url": "https://a.example/3", "description": "z"},
        ]
        articles, keywords = client.build_articles_and_keywords(
            items, "разбор", recent_titles=["Старая статья"]
        )
        self.assertEqual(len(captured), 3)
        self.assertIn("Старая статья", captured[0])
        self.assertNotIn("{n}", captured[0])
        self.assertNotIn("{limit}", captured[0])
        self.assertIn("Агент стёр прод", captured[1])
        self.assertIn("Ещё про стёртый прод", captured[1])
        self.assertNotIn("Бот выдумал скидку", captured[1])
        self.assertEqual(len(articles), 2)
        self.assertEqual(
            articles[0]["source_urls"], ["https://a.example/1", "https://a.example/3"]
        )
        self.assertEqual(articles[1]["source_urls"], ["https://b.example/2"])
        self.assertEqual(keywords, ["агентные права"])

    _TWO_TOPICS_PLAN = (
        '{"topics":['
        '{"topic":"Первая","angle":"а","why_together":"","item_ids":[1]},'
        '{"topic":"Вторая","angle":"б","why_together":"","item_ids":[2]}'
        '],"keywords":[]}'
    )
    _TWO_ITEMS = [
        {"title": "Материал 1", "url": "https://a.example/1", "description": "x"},
        {"title": "Материал 2", "url": "https://b.example/2", "description": "y"},
    ]

    def test_articles_per_run_limits_topics(self):
        from utils.deepseek import DeepSeekClient, clear_prompts_cache

        clear_prompts_cache()
        client = DeepSeekClient(api_key="test-key")
        calls = []

        def fake_chat(messages, temperature=0.7, max_tokens=None):
            calls.append(1)
            if len(calls) == 1:
                return self._TWO_TOPICS_PLAN
            return '{"title":"Заголовок","body":"Текст","rationale":""}'

        client._chat = fake_chat
        articles, _ = client.build_articles_and_keywords(
            self._TWO_ITEMS, "разбор", articles_per_run=1
        )
        self.assertEqual(len(articles), 1)
        self.assertEqual(len(calls), 2)
        self.assertEqual(articles[0]["source_urls"], ["https://a.example/1"])

    def test_failed_article_request_skips_only_that_article(self):
        from utils.deepseek import DeepSeekClient, clear_prompts_cache

        clear_prompts_cache()
        client = DeepSeekClient(api_key="test-key")
        calls = []

        def fake_chat(messages, temperature=0.7, max_tokens=None):
            calls.append(1)
            if len(calls) == 1:
                return self._TWO_TOPICS_PLAN
            if len(calls) == 3:
                raise requests.ConnectionError("network unreachable")
            return '{"title":"Первая статья","body":"Текст","rationale":""}'

        client._chat = fake_chat
        with self.assertLogs("utils.deepseek", level="ERROR") as cm:
            articles, _ = client.build_articles_and_keywords(self._TWO_ITEMS, "разбор")
        self.assertEqual(len(calls), 3)
        self.assertEqual([a["title"] for a in articles], ["Первая статья"])
        self.assertTrue(any("Вторая" in m and "не написана" in m for m in cm.output))

    def test_chat_logs_truncation_by_max_tokens(self):
        from utils.deepseek import DeepSeekClient

        client = DeepSeekClient(api_key="test-key")
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {
            "choices": [
                {"finish_reason": "length", "message": {"content": " обрезанный ответ "}}
            ]
        }
        with patch("utils.deepseek.requests.post", return_value=resp):
            with self.assertLogs("utils.deepseek", level="WARNING") as cm:
                result = client._chat([{"role": "user", "content": "x"}], max_tokens=8192)
        self.assertEqual(result, "обрезанный ответ")
        self.assertTrue(any("обрезан" in m and "8192" in m for m in cm.output))

    def test_empty_plan_gives_no_articles(self):
        from utils.deepseek import DeepSeekClient, clear_prompts_cache

        clear_prompts_cache()
        client = DeepSeekClient(api_key="test-key")
        calls = []

        def fake_chat(messages, temperature=0.7, max_tokens=None):
            calls.append(1)
            return '{"topics":[],"keywords":[]}'

        client._chat = fake_chat
        articles, _ = client.build_articles_and_keywords(
            [{"title": "Т", "url": "", "description": ""}], "разбор"
        )
        self.assertEqual(articles, [])
        self.assertEqual(len(calls), 1)

    @staticmethod
    def _tool_response(payload):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = payload
        return resp

    def test_plan_has_only_titles_without_item_texts(self):
        from utils.deepseek import DeepSeekClient, clear_prompts_cache

        clear_prompts_cache()
        client = DeepSeekClient(api_key="test-key")
        captured = []

        def fake_chat(messages, temperature=0.7, max_tokens=None):
            captured.append(messages[1]["content"])
            return '{"topics":[],"keywords":[]}'

        client._chat = fake_chat
        items = [
            {
                "title": "Заголовок новости",
                "source": "HN",
                "url": "https://a.example/1",
                "description": "СЕКРЕТНЫЙ-ТЕКСТ-МАТЕРИАЛА",
            }
        ]
        client.build_articles_and_keywords(items, "разбор", articles_per_run=5)
        self.assertEqual(len(captured), 1)
        self.assertIn("Заголовок новости", captured[0])
        self.assertIn("[HN]", captured[0])
        self.assertIn("5", captured[0])
        self.assertNotIn("СЕКРЕТНЫЙ-ТЕКСТ-МАТЕРИАЛА", captured[0])
        self.assertNotIn("https://a.example/1", captured[0])

    def test_topics_cut_to_limit_in_model_order(self):
        from utils.deepseek import DeepSeekClient, clear_prompts_cache

        clear_prompts_cache()
        client = DeepSeekClient(api_key="test-key")
        plan = (
            '{"topics":['
            '{"topic":"Т3","angle":"","why_together":"","item_ids":[3]},'
            '{"topic":"Т1","angle":"","why_together":"","item_ids":[1]},'
            '{"topic":"Т2","angle":"","why_together":"","item_ids":[2]}'
            '],"keywords":[]}'
        )
        captured = []

        def fake_chat(messages, temperature=0.7, max_tokens=None):
            captured.append(messages[1]["content"])
            if len(captured) == 1:
                return plan
            return '{"title":"З","body":"Т","rationale":""}'

        client._chat = fake_chat
        items = [
            {"title": f"Материал {i}", "url": f"https://x.example/{i}", "description": ""}
            for i in (1, 2, 3)
        ]
        with self.assertLogs("utils.deepseek", level="INFO") as cm:
            articles, _ = client.build_articles_and_keywords(
                items, "разбор", articles_per_run=2
            )
        self.assertEqual(len(captured), 3)
        self.assertIn("Тема: Т3", captured[1])
        self.assertIn("Тема: Т1", captured[2])
        self.assertEqual(
            [a["source_urls"] for a in articles],
            [["https://x.example/3"], ["https://x.example/1"]],
        )
        log = "\n".join(cm.output)
        self.assertIn("Т3", log)
        self.assertIn("https://x.example/3", log)
        self.assertNotIn("Т2", log)

    _SEARCH_PLAN = (
        '{"topics":[{"topic":"Релиз","angle":"а","why_together":"",'
        '"item_ids":[1],"search_queries":["release details"]}],"keywords":[]}'
    )
    _ONE_ITEM = [
        {"title": "Материал 1", "url": "https://a.example/1", "description": "RSS-ТЕКСТ"}
    ]

    def _client_with_article_capture(self):
        from utils.deepseek import DeepSeekClient, clear_prompts_cache

        clear_prompts_cache()
        client = DeepSeekClient(api_key="test-key")
        captured = []

        def fake_chat(messages, temperature=0.7, max_tokens=None):
            captured.append(messages[1]["content"])
            if len(captured) == 1:
                return self._SEARCH_PLAN
            return '{"title":"Статья","body":"Текст","rationale":""}'

        client._chat = fake_chat
        return client, captured

    def test_fetch_and_search_results_reach_article_and_source_urls(self):
        from utils.deepseek import FETCH_URL, SEARCH_URL

        client, captured = self._client_with_article_capture()
        search_payload = {
            "results": [
                {"rerank_score": 2.5, "title": "Хороший", "url": "https://s.example/good",
                 "content": "ПОИСК-КОНТЕНТ", "summary": "x"},
                {"rerank_score": 1.0, "title": "Слабый", "url": "https://s.example/weak",
                 "content": "СЛАБЫЙ-КОНТЕНТ"},
                {"rerank_score": 1.5, "title": "Дубль", "url": "https://a.example/1",
                 "content": "ДУБЛЬ-КОНТЕНТ"},
                {"rerank_score": 1.5, "title": "Саммари", "url": "https://s.example/sum",
                 "content": "", "summary": "ПОИСК-САММАРИ"},
            ]
        }
        posted = []

        def fake_post(url, headers=None, json=None, timeout=None):
            posted.append((url, json))
            if url == FETCH_URL:
                return self._tool_response({"title": "t", "content": "ПОЛНЫЙ-ТЕКСТ"})
            if url == SEARCH_URL:
                return self._tool_response(search_payload)
            raise AssertionError(url)

        with patch("utils.deepseek.requests.post", side_effect=fake_post):
            articles, _ = client.build_articles_and_keywords(
                self._ONE_ITEM, "разбор", web_tools=True
            )
        self.assertEqual(posted[0], (FETCH_URL, {"url": "https://a.example/1"}))
        self.assertEqual(posted[1][0], SEARCH_URL)
        self.assertEqual(posted[1][1]["query"], "release details")
        self.assertTrue(posted[1][1]["need_content"])
        prompt = captured[1]
        self.assertIn("RSS-ТЕКСТ", prompt)
        self.assertIn("ПОЛНЫЙ-ТЕКСТ", prompt)
        self.assertIn("ПОИСК-КОНТЕНТ", prompt)
        self.assertIn("ПОИСК-САММАРИ", prompt)
        self.assertNotIn("СЛАБЫЙ-КОНТЕНТ", prompt)
        self.assertNotIn("ДУБЛЬ-КОНТЕНТ", prompt)
        self.assertEqual(
            articles[0]["source_urls"],
            ["https://a.example/1", "https://s.example/good", "https://s.example/sum"],
        )

    def test_fetch_and_search_errors_do_not_break_article(self):
        client, captured = self._client_with_article_capture()
        err_resp = MagicMock()
        err_resp.raise_for_status.side_effect = requests.HTTPError("429 Too Many Requests")

        with patch("utils.deepseek.requests.post", return_value=err_resp):
            with self.assertLogs("utils.deepseek", level="WARNING") as cm:
                articles, _ = client.build_articles_and_keywords(
                    self._ONE_ITEM, "разбор", web_tools=True
                )
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["source_urls"], ["https://a.example/1"])
        self.assertIn("RSS-ТЕКСТ", captured[1])
        self.assertTrue(any("Fetch" in m for m in cm.output))
        self.assertTrue(any("Search" in m for m in cm.output))

    def test_web_tools_disabled_makes_no_tool_requests(self):
        from utils.config import Config

        client, captured = self._client_with_article_capture()
        with patch.object(Config, "DEEPSEEK_WEB_TOOLS", False):
            with patch("utils.deepseek.requests.post") as post:
                articles, _ = client.build_articles_and_keywords(self._ONE_ITEM, "разбор")
        post.assert_not_called()
        self.assertEqual(len(articles), 1)
        self.assertIn("RSS-ТЕКСТ", captured[1])
        self.assertEqual(articles[0]["source_urls"], ["https://a.example/1"])

    def test_plan_parses_search_queries(self):
        from utils.deepseek import _parse_plan_payload

        raw = (
            '{"topics":[{"topic":"А","item_ids":[1],'
            '"search_queries":["  q1 ", "", "' + "x" * 200 + '", "q3"]},'
            '{"topic":"Б","item_ids":[2]}],"keywords":[]}'
        )
        topics, _ = _parse_plan_payload(raw, item_count=2)
        self.assertEqual(topics[0]["search_queries"], ["q1", "x" * 128])
        self.assertEqual(topics[1]["search_queries"], [])


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


class ArticleEditApiTests(unittest.TestCase):
    """Правка и удаление статьи через JSON API, временная БД."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self._tmp.name, "test.db")
        self.db = NewsDatabase(self.db_path)
        import web as web_mod

        self.web_mod = web_mod
        self._orig_get_db = web_mod.get_db
        web_mod.get_db = lambda: self.db
        self.client = web_mod.app.test_client()
        self.run_id = self.db.create_run(7)
        self.db.save_articles(
            self.run_id,
            [
                {
                    "title": "Старый заголовок",
                    "body": "Старый текст",
                    "rationale": "Старое обоснование",
                    "source_urls": ["https://old.example/a"],
                }
            ],
        )
        self.article_id = self.db.get_articles_for_run(self.run_id)[0]["id"]

    def tearDown(self):
        self.web_mod.get_db = self._orig_get_db
        self.db.close()
        self._tmp.cleanup()

    def _put(self, article_id, payload):
        return self.client.put(
            f"/api/articles/{article_id}",
            json=payload,
            headers={"X-Requested-With": "fetch"},
        )

    def test_update_normalizes_source_urls(self):
        resp = self._put(
            self.article_id,
            {
                "title": "  Новый заголовок ",
                "body": " Новый текст\nвторая строка ",
                "rationale": " Новое обоснование ",
                "source_urls": [
                    "  https://a.example/1  ",
                    "",
                    "   ",
                    "http://b.example/2",
                    "https://a.example/1",
                    "https://c.example/3",
                ],
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["ok"])
        expected_urls = [
            "https://a.example/1",
            "http://b.example/2",
            "https://c.example/3",
        ]
        self.assertEqual(data["article"]["source_urls"], expected_urls)
        self.assertEqual(data["article"]["title"], "Новый заголовок")
        stored = self.db.get_article(self.article_id)
        self.assertEqual(stored["title"], "Новый заголовок")
        self.assertEqual(stored["body"], "Новый текст\nвторая строка")
        self.assertEqual(stored["rationale"], "Новое обоснование")
        self.assertEqual(stored["source_urls"], expected_urls)

        resp = self._put(
            self.article_id,
            {"title": "Т", "body": "Б", "source_urls": []},
        )
        self.assertEqual(resp.status_code, 200)
        stored = self.db.get_article(self.article_id)
        self.assertEqual(stored["source_urls"], [])
        self.assertEqual(stored["rationale"], "Новое обоснование")

    def test_invalid_url_rejected_without_changes(self):
        for bad in ("ftp://files.example/x", "javascript:alert(1)", "example.com/page"):
            resp = self._put(
                self.article_id,
                {"title": "Новый", "body": "Текст", "source_urls": ["https://ok.example", bad]},
            )
            self.assertEqual(resp.status_code, 400, bad)
            data = resp.get_json()
            self.assertFalse(data["ok"])
            self.assertIn("Некорректная ссылка", data["error"])
            self.assertIn(bad, data["error"])
        stored = self.db.get_article(self.article_id)
        self.assertEqual(stored["title"], "Старый заголовок")
        self.assertEqual(stored["source_urls"], ["https://old.example/a"])

    def test_empty_title_or_body_rejected(self):
        resp = self._put(self.article_id, {"title": "   ", "body": "Текст", "source_urls": []})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Заголовок", resp.get_json()["error"])
        resp = self._put(self.article_id, {"title": "Заголовок", "body": "  ", "source_urls": []})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Текст", resp.get_json()["error"])
        resp = self.client.put(f"/api/articles/{self.article_id}", data="not json")
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.get_json()["ok"])
        self.assertEqual(self.db.get_article(self.article_id)["title"], "Старый заголовок")

    def test_missing_article_returns_404(self):
        resp = self._put(99999, {"title": "Т", "body": "Б", "source_urls": []})
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.get_json(), {"ok": False, "error": "Статья не найдена"})
        resp = self.client.delete("/api/articles/99999")
        self.assertEqual(resp.status_code, 404)
        self.assertFalse(resp.get_json()["ok"])

    def test_delete_removes_article_from_run(self):
        resp = self.client.delete(
            f"/api/articles/{self.article_id}", headers={"X-Requested-With": "fetch"}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"ok": True})
        self.assertIsNone(self.db.get_article(self.article_id))
        self.assertEqual(self.client.get(f"/api/articles/{self.article_id}").status_code, 404)
        run_data = self.client.get(f"/api/runs/{self.run_id}").get_json()
        self.assertEqual(run_data["articles"], [])

    def test_article_view_has_edit_and_delete_without_v_html(self):
        src_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "frontend",
            "src",
            "views",
            "ArticleView.vue",
        )
        with open(src_path, encoding="utf-8") as f:
            src = f.read()
        for text in ("Редактировать", "Сохранить", "Отмена", "Добавить ссылку", "Удалить пост"):
            self.assertIn(text, src)
        self.assertIn("is-busy", src)
        self.assertIn("confirm(", src)
        self.assertIn('method: "DELETE"', src)
        self.assertIn('method: "PUT"', src)
        self.assertNotIn("v-html", src)


def main():

    print("Локальные тесты AI News Aggregator (без сети / Telegram / браузера)")
    print("=" * 60)
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
