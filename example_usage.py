#!/usr/bin/env python3
"""
Пример использования AI News Aggregator
Демонстрирует различные способы использования агрегатора
"""

import sys
import os
from datetime import datetime

# Добавляем текущую директорию в путь для импортов
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from main import AINewsAggregator
from utils.config import Config, setup_logging
from utils.filters import NewsFilter
from utils.telegram_sender import TelegramSender

def example_basic_usage():
    """Базовый пример использования"""
    print("🔍 Пример 1: Базовое использование")
    
    # Создаем агрегатор
    aggregator = AINewsAggregator()
    
    # Запускаем сбор новостей
    all_news, sources_used, errors = aggregator.collect_news()
    
    print(f"Найдено новостей: {len(all_news)}")
    print(f"Источники: {', '.join(sources_used)}")
    print(f"Ошибки: {len(errors)}")
    
    return all_news

def example_custom_filtering():
    """Пример с кастомной фильтрацией"""
    print("\n🔍 Пример 2: Кастомная фильтрация")
    
    # Создаем фильтр
    filter_obj = NewsFilter()
    
    # Тестовые новости
    test_news = [
        {
            'title': 'OpenAI представила GPT-5 с новыми возможностями',
            'url': 'https://example.com/gpt5',
            'source': 'Test Source',
            'published_date': datetime.now(),
            'keywords': ['OpenAI', 'GPT-5']
        },
        {
            'title': 'Исследование потери функции в нейронных сетях',
            'url': 'https://example.com/research',
            'source': 'Test Source',
            'published_date': datetime.now(),
            'keywords': ['research', 'neural networks']
        }
    ]
    
    # Фильтруем по релевантности
    relevant_news = filter_obj.filter_news_by_relevance(test_news, min_score=50)
    
    print(f"Исходных новостей: {len(test_news)}")
    print(f"После фильтрации: {len(relevant_news)}")
    
    for news in relevant_news:
        print(f"  - {news['title']} (релевантность: {news.get('relevance_score', 0)})")

def example_telegram_integration():
    """Пример интеграции с Telegram"""
    print("\n🔍 Пример 3: Telegram интеграция")
    
    # Создаем отправитель
    sender = TelegramSender()
    
    # Тестовое сообщение
    test_message = """
📰 *AI News Digest — Тест*

🔹 [OpenAI представила GPT-5](https://example.com)
Источник: Test Source

🔹 [Новые возможности ChatGPT](https://example.com)
Источник: Test Source
"""
    
    # Отправляем сообщение
    success = sender.send_message(test_message)
    
    if success:
        print("✅ Тестовое сообщение отправлено")
    else:
        print("❌ Ошибка отправки сообщения")

def example_source_specific():
    """Пример работы с конкретными источниками"""
    print("\n🔍 Пример 4: Работа с конкретными источниками")
    
    config = Config()
    
    # Проверяем доступные источники
    sources = []
    
    if config.ENABLE_TWITTER:
        try:
            from sources.twitter_parser import TwitterParser
            twitter_parser = TwitterParser()
            twitter_news = twitter_parser.search_tweets(max_results=5)
            sources.append(('Twitter', len(twitter_news)))
        except Exception as e:
            sources.append(('Twitter', f"Ошибка: {e}"))
    
    if config.ENABLE_GOOGLE_NEWS:
        try:
            from sources.google_news_parser import GoogleNewsParser
            google_parser = GoogleNewsParser()
            google_news = google_parser.search_news(max_results=5)
            sources.append(('Google News', len(google_news)))
        except Exception as e:
            sources.append(('Google News', f"Ошибка: {e}"))

    if config.ENABLE_YOUTUBE:
        try:
            from sources.youtube_parser import YouTubeParser
            youtube_parser = YouTubeParser()
            youtube_news = youtube_parser.search_videos(max_results=5)
            sources.append(('YouTube', len(youtube_news)))
        except Exception as e:
            sources.append(('YouTube', f"Ошибка: {e}"))
    
    # Выводим результаты
    for source_name, result in sources:
        print(f"  {source_name}: {result}")

def example_scheduled_run():
    """Пример запуска по расписанию"""
    print("\n🔍 Пример 5: Запуск по расписанию")
    
    print("Для автоматического запуска используйте:")
    print("  python scheduler.py")
    print("\nИли настройте cron:")
    print("  0 9 * * * cd /path/to/project && python main.py")

def main():
    """Основная функция с примерами"""
    print("📚 Примеры использования AI News Aggregator")
    print("=" * 50)
    
    # Настраиваем логирование
    logger = setup_logging()
    
    try:
        # Запускаем примеры
        example_basic_usage()
        example_custom_filtering()
        example_telegram_integration()
        example_source_specific()
        example_scheduled_run()
        
        print("\n✅ Все примеры выполнены успешно!")
        
    except Exception as e:
        print(f"\n❌ Ошибка при выполнении примеров: {e}")

if __name__ == "__main__":
    main()
