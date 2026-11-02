#!/usr/bin/env python3
"""
AI News Aggregator — полный недельный прогон:
сбор → фильтр → DeepSeek → SQLite → одно уведомление в Telegram.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.ssl_trust import use_system_certificates

use_system_certificates()

from utils.config import Config, setup_logging
from utils.db import NewsDatabase
from utils.deepseek import DeepSeekClient
from utils.filters import NewsFilter, build_run_ready_notification
from utils.telegram_sender import TelegramSender



MANUAL_SOURCE = "Вручную"
MANUAL_TITLE_LANGUAGE_ERROR = "Заголовок должен быть на русском или английском"


class AINewsAggregator:
    def __init__(self, db: Optional[NewsDatabase] = None):
        self.config = Config()
        self.db = db if db is not None else NewsDatabase()
        self.active_keywords = self.db.get_active_keywords()
        self.filter = NewsFilter(self.active_keywords)
        self.logger = logging.getLogger(__name__)
        self.telegram_sender: Optional[TelegramSender] = None

    def _telegram(self) -> TelegramSender:
        if self.telegram_sender is None:
            self.telegram_sender = TelegramSender()
        return self.telegram_sender

    def process_news(self, news_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        self.logger.info("Обрабатываем собранные материалы...")
        unique_news = self.filter.remove_duplicates(news_list)
        self.logger.info("После дубликатов: %s", len(unique_news))

        relevant_news = self.filter.filter_news_by_relevance(unique_news, min_score=20)
        self.logger.info("После релевантности: %s", len(relevant_news))

        def _published_ts(item: Dict[str, Any]) -> float:
            published = item.get("published_date")
            if isinstance(published, datetime):
                return published.timestamp()
            return 0.0

        relevant_news.sort(
            key=lambda x: (x.get("ranking_score", 0), _published_ts(x)),
            reverse=True,
        )
        before = len(relevant_news)
        relevant_news = self.filter.drop_similar_titles(relevant_news)
        if len(relevant_news) < before:
            self.logger.info("Похожие заголовки: %s → %s", before, len(relevant_news))

        # DIGEST_MAX_ITEMS больше не обрезает материалы для модели
        return relevant_news

    def process_manual_items(self, news_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Свои тексты: дубли и похожие заголовки как у прогона, без порога релевантности."""
        self.logger.info("Обрабатываем свои тексты...")
        unique_news = self.filter.remove_duplicates(news_list)
        self.logger.info("После дубликатов: %s", len(unique_news))

        kept = [
            item
            for item in unique_news
            if self.filter.title_letters_are_ru_or_en(item.get("title", ""))
        ]
        self.logger.info("После языка заголовка: %s", len(kept))

        before = len(kept)
        kept = self.filter.drop_similar_titles(kept)
        if len(kept) < before:
            self.logger.info("Похожие заголовки: %s → %s", before, len(kept))
        return kept

    def collect_news(self) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Собирает новости. Возвращает (items, protocol_notes)."""
        all_news: List[Dict[str, Any]] = []
        protocol: List[str] = []
        keywords = self.active_keywords

        def note_disabled(name: str) -> None:
            msg = f"{name}: отключён в .env"
            protocol.append(msg)
            self.logger.warning(msg)

        # Google News
        if self.config.ENABLE_GOOGLE_NEWS:
            try:
                from sources.google_news_parser import GoogleNewsParser

                parser = GoogleNewsParser(keywords)
                items = parser.search_news(max_results=self.config.GOOGLE_NEWS_MAX)
                all_news.extend(items)
                self.logger.info("Google News: %s", len(items))
            except Exception as e:
                msg = f"Google News: {e}"
                protocol.append(msg)
                self.logger.error(msg)
        else:
            note_disabled("Google News")

        # Hacker News
        if self.config.ENABLE_HACKERNEWS:
            try:
                from sources.hackernews_parser import HackerNewsParser

                parser = HackerNewsParser(keywords)
                items = parser.search_stories(max_results=self.config.HACKERNEWS_MAX)
                all_news.extend(items)
                self.logger.info("Hacker News: %s", len(items))
            except Exception as e:
                msg = f"Hacker News: {e}"
                protocol.append(msg)
                self.logger.error(msg)
        else:
            note_disabled("Hacker News")

        # Reddit AI + business
        if self.config.ENABLE_REDDIT:
            try:
                from sources.reddit_parser import RedditParser

                parser = RedditParser(keywords)
                ai_posts = parser.search_posts(max_results=self.config.REDDIT_AI_MAX)
                biz_posts = parser.search_business_posts(max_results=self.config.REDDIT_BUSINESS_MAX)
                all_news.extend(ai_posts)
                all_news.extend(biz_posts)
                self.logger.info("Reddit AI: %s, business: %s", len(ai_posts), len(biz_posts))
            except Exception as e:
                msg = f"Reddit: {e}"
                protocol.append(msg)
                self.logger.error(msg)
        else:
            note_disabled("Reddit")

        self.logger.info("Всего сырых материалов: %s", len(all_news))
        return all_news, protocol

    def complete_run(self, processed: List[Dict[str, Any]], protocol_text: str = "") -> int:
        """DeepSeek, запись в SQLite и одно уведомление в Telegram.

        Вызывается и обычным прогоном, и разбором своих текстов.
        Если ошибка после создания прогона — статус failed, исключение пробрасывается.
        В Telegram ошибку не отправляем.
        """
        run_id: Optional[int] = None
        try:
            run_id = self.db.create_run(self.config.NEWS_LOOKBACK_DAYS)
            self.db.save_items(run_id, processed)

            client = DeepSeekClient()
            summary = client.build_weekly_analysis(processed)
            articles, proposed = client.build_articles_and_keywords(
                processed,
                summary,
                recent_titles=self.db.get_recent_article_titles(),
            )

            self.db.save_summary(run_id, summary)
            self.db.save_articles(run_id, articles)
            added = self.db.propose_keywords(proposed, run_id)
            self.logger.info("Статей: %s, новых proposed-ключей: %s", len(articles), added)

            self.db.finish_run(run_id, status="ok", error_text=protocol_text)
            self._send_success_notification(run_id)
            self.logger.info("Прогон завершён успешно")
            return run_id
        except Exception as e:
            if run_id is not None:
                self.db.finish_run(run_id, status="failed", error_text=str(e))
            raise

    def run(self) -> None:
        try:
            self.logger.info("Запуск полного недельного прогона...")
            self.config.validate_config()

            all_news, protocol = self.collect_news()
            processed = self.process_news(all_news) if all_news else []
            protocol_text = "\n".join(protocol)

            if protocol:
                self.logger.info("Протокол источников:\n%s", protocol_text)

            if not processed:
                self.logger.info(
                    "Пустой прогон: после фильтров нет материалов "
                    "(lookback=%s дн.). В SQLite и Telegram ничего не пишем.",
                    self.config.NEWS_LOOKBACK_DAYS,
                )
                return

            self.complete_run(processed, protocol_text)

        except Exception as e:
            self.logger.error("Критическая ошибка прогона: %s", e)
            # В Telegram ошибку не отправляем. Статус failed ставит complete_run.

    def run_manual(self, items: List[Dict[str, Any]]) -> int:
        """Разбор уже отобранных текстов без сбора источников. Возвращает run_id."""
        self.logger.info("Запуск разбора своих текстов...")
        self.config.validate_config()
        processed = self.process_manual_items(items)
        if not processed:
            self.logger.info(
                "Пустой ручной прогон: после фильтров нет материалов. "
                "В SQLite и Telegram ничего не пишем."
            )
            raise ValueError(MANUAL_TITLE_LANGUAGE_ERROR)
        return self.complete_run(processed, "")

    def _send_success_notification(self, run_id: int) -> None:
        message = build_run_ready_notification(self.config.WEB_URL)
        ok = self._telegram().send_message(message, parse_mode=None)
        if ok:
            self.db.mark_telegram_sent(run_id)
        else:
            self.logger.error("Не удалось отправить уведомление в Telegram")

    def test_sources(self) -> None:
        """Проверка источников без Telegram и без записи разбора."""
        self.logger.info("Тестирование источников (без Telegram / без записи разбора)...")
        keywords = self.active_keywords

        if self.config.ENABLE_GOOGLE_NEWS:
            try:
                from sources.google_news_parser import GoogleNewsParser

                n = len(GoogleNewsParser(keywords).search_news(max_results=1))
                self.logger.info("Google News: OK (%s)", n)
            except Exception as e:
                self.logger.error("Google News: %s", e)

        if self.config.ENABLE_HACKERNEWS:
            try:
                from sources.hackernews_parser import HackerNewsParser

                n = len(HackerNewsParser(keywords).search_stories(max_results=1))
                self.logger.info("Hacker News: OK (%s)", n)
            except Exception as e:
                self.logger.error("Hacker News: %s", e)

        if self.config.ENABLE_REDDIT:
            try:
                from sources.reddit_parser import RedditParser

                n = len(RedditParser(keywords).search_posts(max_results=1))
                self.logger.info("Reddit: OK (%s)", n)
            except Exception as e:
                self.logger.error("Reddit: %s", e)


def _manual_item_url(raw: Dict[str, Any]) -> str:
    """Опциональный URL пары: поле url или link; пустая строка допустима."""
    for key in ("url", "link"):
        value = raw.get(key)
        if isinstance(value, str):
            return value.strip()
    return ""


def normalize_manual_pairs(pairs: List[Any]) -> List[Dict[str, Any]]:
    """Полные пары заголовок+текст становятся материалами с description."""
    now = datetime.now(timezone.utc)
    items: List[Dict[str, Any]] = []
    for raw in pairs:
        if not isinstance(raw, dict):
            continue
        title = raw.get("title")
        text = raw.get("text")
        if not isinstance(title, str) or not isinstance(text, str):
            continue
        title = title.strip()
        text = text.strip()
        if not title or not text:
            continue
        items.append(
            {
                "title": title,
                "description": text,
                "source": MANUAL_SOURCE,
                "url": _manual_item_url(raw),
                "published_date": now,
            }
        )
    return items


def main():
    logger = setup_logging()
    try:
        cli_arg = sys.argv[1] if len(sys.argv) > 1 else None

        if cli_arg == "--test":
            aggregator = AINewsAggregator()
            aggregator.test_sources()
            return

        if cli_arg is not None:
            logger.error(
                "Неизвестный аргумент %s. Допустимо: python main.py или python main.py --test",
                cli_arg,
            )
            sys.exit(2)

        aggregator = AINewsAggregator()
        aggregator.run()

    except KeyboardInterrupt:
        logger.info("Программа прервана пользователем")
    except Exception as e:
        logger.error("Критическая ошибка: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
