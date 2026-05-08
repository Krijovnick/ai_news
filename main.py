#!/usr/bin/env python3
"""
AI News Aggregator - Основной файл
Собирает новости об ИИ из различных источников и отправляет в Telegram
"""

import logging
import os
import sys
from datetime import datetime
from typing import List, Dict, Any

# Добавляем текущую директорию в путь для импортов
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.config import Config, setup_logging
from utils.filters import NewsFilter
from utils.telegram_sender import TelegramSender
from utils.summarizer import ArticleSummarizer
from sources.twitter_parser import TwitterParser
from sources.google_news_parser import GoogleNewsParser
from sources.hackernews_parser import HackerNewsParser
from sources.reddit_parser import RedditParser
from sources.youtube_parser import YouTubeParser

class AINewsAggregator:
    """Основной класс агрегатора новостей об ИИ"""
    
    def __init__(self):
        self.config = Config()
        self.filter = NewsFilter()
        self.telegram_sender = TelegramSender()
        # Суммаризатор включаем только если это разрешено в конфиге
        self.summarizer = ArticleSummarizer() if self.config.ENABLE_SUMMARIZER else None
        self.logger = logging.getLogger(__name__)
        
        # Инициализируем парсеры
        self.parsers = {}
        self._initialize_parsers()
    
    def _initialize_parsers(self):
        """Инициализирует парсеры для доступных источников"""
        
        try:
            if self.config.ENABLE_TWITTER:
                self.parsers['twitter'] = TwitterParser()
                self.logger.info("Twitter парсер инициализирован")
        except Exception as e:
            self.logger.error(f"Ошибка инициализации Twitter парсера: {e}")
        
        try:
            if self.config.ENABLE_GOOGLE_NEWS:
                self.parsers['google_news'] = GoogleNewsParser()
                self.logger.info("Google News парсер инициализирован")
        except Exception as e:
            self.logger.error(f"Ошибка инициализации Google News парсера: {e}")
        
        try:
            if self.config.ENABLE_HACKERNEWS:
                self.parsers['hackernews'] = HackerNewsParser()
                self.logger.info("Hacker News парсер инициализирован")
        except Exception as e:
            self.logger.error(f"Ошибка инициализации Hacker News парсера: {e}")
        
        try:
            if self.config.ENABLE_REDDIT:
                self.parsers['reddit'] = RedditParser()
                self.logger.info("Reddit парсер инициализирован")
        except Exception as e:
            self.logger.error(f"Ошибка инициализации Reddit парсера: {e}")

        try:
            if self.config.ENABLE_YOUTUBE:
                self.parsers['youtube'] = YouTubeParser()
                self.logger.info("YouTube парсер инициализирован")
        except Exception as e:
            self.logger.error(f"Ошибка инициализации YouTube парсера: {e}")
    
    def collect_news(self) -> List[Dict[str, Any]]:
        """Собирает новости из всех доступных источников"""
        all_news = []
        sources_used = []
        errors = []
        
        self.logger.info("Начинаем сбор новостей...")
        
        # Twitter
        if 'twitter' in self.parsers:
            try:
                twitter_news = self.parsers['twitter'].search_tweets(max_results=60)
                all_news.extend(twitter_news)
                sources_used.append('Twitter')
                self.logger.info(f"Twitter: найдено {len(twitter_news)} новостей")
            except Exception as e:
                error_msg = f"Twitter: {str(e)}"
                errors.append(error_msg)
                self.logger.error(error_msg)
        
        # Google News
        if 'google_news' in self.parsers:
            try:
                google_news = self.parsers['google_news'].search_news(max_results=60)
                all_news.extend(google_news)
                sources_used.append('Google News')
                self.logger.info(f"Google News: найдено {len(google_news)} новостей")
            except Exception as e:
                error_msg = f"Google News: {str(e)}"
                errors.append(error_msg)
                self.logger.error(error_msg)
        
        # Hacker News
        if 'hackernews' in self.parsers:
            try:
                hackernews_news = self.parsers['hackernews'].search_stories(max_results=50)
                all_news.extend(hackernews_news)
                sources_used.append('Hacker News')
                self.logger.info(f"Hacker News: найдено {len(hackernews_news)} новостей")
            except Exception as e:
                error_msg = f"Hacker News: {str(e)}"
                errors.append(error_msg)
                self.logger.error(error_msg)
        
        # Reddit
        if 'reddit' in self.parsers:
            try:
                reddit_news = self.parsers['reddit'].search_posts(max_results=50)
                all_news.extend(reddit_news)
                sources_used.append('Reddit')
                self.logger.info(f"Reddit: найдено {len(reddit_news)} новостей")
            except Exception as e:
                error_msg = f"Reddit: {str(e)}"
                errors.append(error_msg)
                self.logger.error(error_msg)

        # YouTube
        if 'youtube' in self.parsers:
            try:
                youtube_news = self.parsers['youtube'].search_videos(max_results=50)
                all_news.extend(youtube_news)
                sources_used.append('YouTube')
                self.logger.info(f"YouTube: найдено {len(youtube_news)} видео")
            except Exception as e:
                error_msg = f"YouTube: {str(e)}"
                errors.append(error_msg)
                self.logger.error(error_msg)
        
        self.logger.info(f"Всего собрано {len(all_news)} новостей из {len(sources_used)} источников")
        
        return all_news, sources_used, errors
    
    def process_news(self, news_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Обрабатывает собранные новости"""
        self.logger.info("Обрабатываем собранные новости...")
        
        # Удаляем дубликаты
        unique_news = self.filter.remove_duplicates(news_list)
        self.logger.info(f"После удаления дубликатов: {len(unique_news)} новостей")
        
        # Фильтруем по релевантности
        relevant_news = self.filter.filter_news_by_relevance(unique_news, min_score=10)
        self.logger.info(f"После фильтрации по релевантности: {len(relevant_news)} новостей")
        
        # Сортируем по итоговому рейтингу (релевантность + популярность),
        # а при равенстве — по дате.
        def _published_ts(item: Dict[str, Any]) -> float:
            published = item.get("published_date")
            if isinstance(published, datetime):
                return published.timestamp()
            return 0.0

        relevant_news.sort(
            key=lambda x: (x.get("ranking_score", 0), _published_ts(x)),
            reverse=True,
        )
        
        return relevant_news

    def process_business_reddit(self, posts: List[Dict[str, Any]], max_items: int = 50) -> List[Dict[str, Any]]:
        """Посты бизнес-Reddit: язык и сортировка по популярности (score)."""
        self.logger.info("Обрабатываем бизнес-посты Reddit...")
        unique_posts = self.filter.remove_duplicates(posts)
        self.logger.info(f"После удаления дубликатов: {len(unique_posts)} постов")
        filtered = self.filter.filter_business_reddit_posts(unique_posts, max_items=max_items)
        self.logger.info(f"После фильтра по языку и среза: {len(filtered)} постов")
        return filtered

    def send_news_digest(
        self,
        news_list: List[Dict[str, Any]],
        sources_used: List[str],
        errors: List[str],
        *,
        feed_title: str = "AI News Digest",
        item_emoji: str = "🧠",
        summary_run_name: str = "AI News Aggregator",
    ):
        """Отправляет новости в Telegram: каждую статью отдельным сообщением с выжимкой."""
        try:
            if not news_list:
                message = (
                    f"📰 <b>{feed_title}</b>\n\n"
                    f"Новостей не найдено за последние {self.config.NEWS_LOOKBACK_DAYS} дней."
                )
                self.telegram_sender.send_message(message, parse_mode="HTML")
                return

            sent_count = 0

            for news in news_list:
                title = news.get("title", "Без заголовка")
                description = news.get("description", "")
                url = news.get("url", "#")
                source = news.get("source", "Неизвестный источник")

                summary = None

                # Если суммаризация включена и суммаризатор инициализирован — пробуем получить выжимку
                if self.summarizer is not None:
                    summary = self.summarizer.summarize_article(
                        title=title,
                        description=description,
                        source=source,
                        url=url,
                        max_sentences=10,
                    )

                if summary is None:
                    # Отправляем без выжимки, только заголовок и ссылку
                    message = (
                        f"{item_emoji} <b>{title}</b>\n\n"
                        f"Источник: {source}\n"
                        f"{url}"
                    )
                else:
                    # Сообщение с заголовком и выжимкой
                    message = (
                        f"{item_emoji} <b>{title}</b>\n\n"
                        f"{summary}\n\n"
                        f"<i>Источник: {source}</i>\n"
                        f"{url}"
                    )

                success = self.telegram_sender.send_message(message, parse_mode="HTML")

                if success:
                    sent_count += 1
                else:
                    self.logger.error(f"Не удалось отправить сообщение для новости: {title}")
            
            # Отправляем сводку
            self.telegram_sender.send_summary(len(news_list), sources_used, errors, run_name=summary_run_name)
            
        except Exception as e:
            self.logger.error(f"Ошибка при отправке дайджеста: {e}")
            self.telegram_sender.send_error_message(str(e))

    def run_reddit_business(self):
        """Только Reddit: популярные бизнес-посты за ~7 дней."""
        try:
            self.logger.info("Запуск Reddit Business digest...")
            self.config.validate_config()
            if not self.config.ENABLE_REDDIT:
                self.logger.error("Reddit отключён в конфиге (ENABLE_REDDIT=false)")
                self.telegram_sender.send_message(
                    "❌ <b>Reddit Business</b>\n\nВключите ENABLE_REDDIT в .env для этого режима.",
                    parse_mode="HTML",
                )
                return
            errors: List[str] = []
            parser = RedditParser()
            raw_posts = parser.search_business_posts(max_results=55)
            if not raw_posts:
                self.logger.warning("Бизнес-посты Reddit не найдены")
                self.telegram_sender.send_message(
                    "📰 <b>Reddit Business Digest</b>\n\n"
                    f"Постов не найдено за последние {self.config.NEWS_LOOKBACK_DAYS} дней.",
                    parse_mode="HTML",
                )
                return
            processed = self.process_business_reddit(raw_posts, max_items=50)
            sources_used = ["Reddit Business"]
            if not processed:
                self.telegram_sender.send_message(
                    "📰 <b>Reddit Business Digest</b>\n\n"
                    "После фильтров постов не осталось.",
                    parse_mode="HTML",
                )
                return
            self.send_news_digest(
                processed,
                sources_used,
                errors,
                feed_title="Reddit Business Digest",
                item_emoji="💼",
                summary_run_name="Reddit Business Digest",
            )
            self.logger.info("Reddit Business digest завершён успешно")
        except Exception as e:
            self.logger.error(f"Критическая ошибка Reddit Business: {e}")
            self.telegram_sender.send_error_message(str(e))

    def run_selected_sources(self, selected_sources: List[str], *, digest_title: str):
        """Запускает дайджест только по выбранным источникам."""
        try:
            self.logger.info("Запуск выборочного дайджеста: %s", ", ".join(selected_sources))
            self.config.validate_config()

            source_configs = {
                "twitter": {
                    "enabled": self.config.ENABLE_TWITTER,
                    "display": "Twitter",
                    "fetcher": lambda: self.parsers["twitter"].search_tweets(max_results=60),
                },
                "google_news": {
                    "enabled": self.config.ENABLE_GOOGLE_NEWS,
                    "display": "Google News",
                    "fetcher": lambda: self.parsers["google_news"].search_news(max_results=60),
                },
                "hackernews": {
                    "enabled": self.config.ENABLE_HACKERNEWS,
                    "display": "Hacker News",
                    "fetcher": lambda: self.parsers["hackernews"].search_stories(max_results=50),
                },
                "reddit": {
                    "enabled": self.config.ENABLE_REDDIT,
                    "display": "Reddit",
                    "fetcher": lambda: self.parsers["reddit"].search_posts(max_results=50),
                },
                "youtube": {
                    "enabled": self.config.ENABLE_YOUTUBE,
                    "display": "YouTube",
                    "fetcher": lambda: self.parsers["youtube"].search_videos(max_results=50),
                },
            }

            all_news: List[Dict[str, Any]] = []
            sources_used: List[str] = []
            errors: List[str] = []

            for source_key in selected_sources:
                config = source_configs.get(source_key)
                if config is None:
                    continue

                if not config["enabled"] or source_key not in self.parsers:
                    errors.append(f"{config['display']}: отключен в .env")
                    self.logger.warning("%s отключен в .env", config["display"])
                    continue

                try:
                    source_news = config["fetcher"]()
                    all_news.extend(source_news)
                    sources_used.append(config["display"])
                    self.logger.info("%s: найдено %s материалов", config["display"], len(source_news))
                except Exception as e:
                    error_msg = f"{config['display']}: {str(e)}"
                    errors.append(error_msg)
                    self.logger.error(error_msg)

            if not all_news:
                self.telegram_sender.send_message(
                    f"📰 *{digest_title}*\n\nНовостей не найдено за последние {self.config.NEWS_LOOKBACK_DAYS} дней."
                )
                return

            processed_news = self.process_news(all_news)
            self.send_news_digest(
                processed_news,
                sources_used,
                errors,
                feed_title=digest_title,
                summary_run_name=digest_title,
            )
        except Exception as e:
            self.logger.error("Критическая ошибка выборочного запуска: %s", e)
            self.telegram_sender.send_error_message(str(e))
    
    def run(self):
        """Основной метод запуска агрегатора"""
        try:
            self.logger.info("Запуск AI News Aggregator...")
            
            # Проверяем конфигурацию
            self.config.validate_config()
            
            # Собираем новости
            all_news, sources_used, errors = self.collect_news()
            
            if not all_news:
                self.logger.warning("Новости не найдены")
                self.telegram_sender.send_message(
                    f"📰 *AI News Digest*\n\nНовостей не найдено за последние {self.config.NEWS_LOOKBACK_DAYS} дней."
                )
                return
            
            # Обрабатываем новости
            processed_news = self.process_news(all_news)
            
            # Отправляем дайджест
            self.send_news_digest(processed_news, sources_used, errors)
            
            self.logger.info("AI News Aggregator завершил работу успешно")
            
        except Exception as e:
            self.logger.error(f"Критическая ошибка в AI News Aggregator: {e}")
            self.telegram_sender.send_error_message(str(e))
    
    def test_sources(self):
        """Тестирует доступность источников"""
        self.logger.info("Тестирование источников...")
        
        for source_name, parser in self.parsers.items():
            try:
                if source_name == 'twitter':
                    test_news = parser.search_tweets(max_results=1)
                elif source_name == 'google_news':
                    test_news = parser.search_news(max_results=1)
                elif source_name == 'hackernews':
                    test_news = parser.search_stories(max_results=1)
                elif source_name == 'reddit':
                    test_news = parser.search_posts(max_results=1)
                elif source_name == 'youtube':
                    test_news = parser.search_videos(max_results=1)
                
                self.logger.info(f"✅ {source_name}: OK")
                
            except Exception as e:
                self.logger.error(f"❌ {source_name}: {e}")

def main():
    """Точка входа в программу"""
    # Настраиваем логирование
    logger = setup_logging()
    
    try:
        # Создаем агрегатор
        aggregator = AINewsAggregator()
        
        # Проверяем аргументы командной строки
        if len(sys.argv) > 1 and sys.argv[1] == '--test':
            aggregator.test_sources()
            return

        if len(sys.argv) > 1 and sys.argv[1] == '--reddit-business':
            aggregator.run_reddit_business()
            return

        if len(sys.argv) > 1 and sys.argv[1] == '--youtube-only':
            aggregator.run_selected_sources(["youtube"], digest_title="YouTube AI Digest")
            return

        if len(sys.argv) > 1 and sys.argv[1] == '--reddit-only':
            aggregator.run_selected_sources(["reddit"], digest_title="Reddit AI Digest")
            return

        if len(sys.argv) > 1 and sys.argv[1] == '--google-hn':
            aggregator.run_selected_sources(["google_news", "hackernews"], digest_title="Google + Hacker News AI Digest")
            return
        
        # Запускаем агрегатор
        aggregator.run()
        
    except KeyboardInterrupt:
        logger.info("Программа прервана пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
