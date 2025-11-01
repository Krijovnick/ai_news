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
from sources.youtube_parser import YouTubeParser
from sources.twitter_parser import TwitterParser
from sources.google_news_parser import GoogleNewsParser
from sources.hackernews_parser import HackerNewsParser
from sources.reddit_parser import RedditParser

class AINewsAggregator:
    """Основной класс агрегатора новостей об ИИ"""
    
    def __init__(self):
        self.config = Config()
        self.filter = NewsFilter()
        self.telegram_sender = TelegramSender()
        self.logger = logging.getLogger(__name__)
        
        # Инициализируем парсеры
        self.parsers = {}
        self._initialize_parsers()
    
    def _initialize_parsers(self):
        """Инициализирует парсеры для доступных источников"""
        try:
            if self.config.ENABLE_YOUTUBE:
                self.parsers['youtube'] = YouTubeParser()
                self.logger.info("YouTube парсер инициализирован")
        except Exception as e:
            self.logger.error(f"Ошибка инициализации YouTube парсера: {e}")
        
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
    
    def collect_news(self) -> List[Dict[str, Any]]:
        """Собирает новости из всех доступных источников"""
        all_news = []
        sources_used = []
        errors = []
        
        self.logger.info("Начинаем сбор новостей...")
        
        # YouTube
        if 'youtube' in self.parsers:
            try:
                youtube_news = self.parsers['youtube'].search_videos(max_results=50)
                all_news.extend(youtube_news)
                sources_used.append('YouTube')
                self.logger.info(f"YouTube: найдено {len(youtube_news)} новостей")
            except Exception as e:
                error_msg = f"YouTube: {str(e)}"
                errors.append(error_msg)
                self.logger.error(error_msg)
        
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
        
        # Сортируем по дате публикации
        relevant_news.sort(key=lambda x: x.get('published_date', datetime.min), reverse=True)
        
        return relevant_news
    
    def send_news_digest(self, news_list: List[Dict[str, Any]], sources_used: List[str], errors: List[str]):
        """Отправляет дайджест новостей в Telegram"""
        try:
            if not news_list:
                message = "📰 *AI News Digest*\n\nНовостей не найдено за последние 24 часа."
                self.telegram_sender.send_message(message)
                return
            
            # Форматируем новости для Telegram (без ограничений)
            formatted_message = self.filter.format_news_for_telegram(news_list, max_items=len(news_list))
            
            # Отправляем дайджест
            success = self.telegram_sender.send_message(formatted_message)
            
            if success:
                self.logger.info("Дайджест новостей успешно отправлен в Telegram")
            else:
                self.logger.error("Ошибка при отправке дайджеста в Telegram")
            
            # Отправляем сводку
            self.telegram_sender.send_summary(len(news_list), sources_used, errors)
            
        except Exception as e:
            self.logger.error(f"Ошибка при отправке дайджеста: {e}")
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
                self.telegram_sender.send_message("📰 *AI News Digest*\n\nНовостей не найдено за последние 24 часа.")
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
                if source_name == 'youtube':
                    test_news = parser.search_videos(max_results=1)
                elif source_name == 'twitter':
                    test_news = parser.search_tweets(max_results=1)
                elif source_name == 'google_news':
                    test_news = parser.search_news(max_results=1)
                elif source_name == 'hackernews':
                    test_news = parser.search_stories(max_results=1)
                elif source_name == 'reddit':
                    test_news = parser.search_posts(max_results=1)
                
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
        
        # Запускаем агрегатор
        aggregator.run()
        
    except KeyboardInterrupt:
        logger.info("Программа прервана пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
