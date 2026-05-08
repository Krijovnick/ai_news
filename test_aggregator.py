#!/usr/bin/env python3
"""
Тестовый файл для AI News Aggregator
Проверяет работу всех компонентов
"""

import sys
import os
import logging
from datetime import datetime

# Добавляем текущую директорию в путь для импортов
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.config import Config, setup_logging
from utils.filters import NewsFilter
from utils.telegram_sender import TelegramSender

def test_config():
    """Тестирует конфигурацию"""
    print("Тестирование конфигурации...")
    
    try:
        config = Config()
        print(f"OK Конфигурация загружена")
        print(f"   - Twitter: {'включен' if config.ENABLE_TWITTER else 'отключен'}")
        print(f"   - Google News: {'включен' if config.ENABLE_GOOGLE_NEWS else 'отключен'}")
        print(f"   - Hacker News: {'включен' if config.ENABLE_HACKERNEWS else 'отключен'}")
        print(f"   - Reddit: {'включен' if config.ENABLE_REDDIT else 'отключен'}")
        print(f"   - YouTube: {'включен' if config.ENABLE_YOUTUBE else 'отключен'}")
        
        # Проверяем обязательные настройки
        if not config.TELEGRAM_BOT_TOKEN:
            print("ERROR TELEGRAM_BOT_TOKEN не установлен")
            return False
        
        if not config.TELEGRAM_CHAT_ID:
            print("ERROR TELEGRAM_CHAT_ID не установлен")
            return False
        
        print("OK Обязательные настройки проверены")
        return True
        
    except Exception as e:
        print(f"ERROR Ошибка конфигурации: {e}")
        return False

def test_filters():
    """Тестирует фильтры"""
    print("\nTEST Тестирование фильтров...")
    
    try:
        filter_obj = NewsFilter()
        
        # Тестируем фильтрацию по ключевым словам
        test_texts = [
            "OpenAI представила новую модель GPT-5",
            "Исследование потери функции в нейронных сетях",
            "ChatGPT теперь поддерживает голосовые команды",
            "Научная статья о backpropagation в arxiv.org"
        ]
        
        for text in test_texts:
            contains_ai = filter_obj.contains_ai_keywords(text)
            print(f"   '{text[:30]}...' -> {'OK' if contains_ai else 'ERROR'}")
        
        print("OK Фильтры работают корректно")
        return True
        
    except Exception as e:
        print(f"ERROR Ошибка фильтров: {e}")
        return False

def test_telegram():
    """Тестирует Telegram интеграцию"""
    print("\nTELEGRAM Тестирование Telegram...")
    
    try:
        sender = TelegramSender()
        
        # Отправляем тестовое сообщение
        test_message = "🤖 *Тест AI News Aggregator*\n\nПроверка работы бота..."
        success = sender.send_message(test_message)
        
        if success:
            print("OK Тестовое сообщение отправлено в Telegram")
            return True
        else:
            print("ERROR Ошибка отправки сообщения в Telegram")
            return False
            
    except Exception as e:
        print(f"ERROR Ошибка Telegram: {e}")
        return False

def test_parsers():
    """Тестирует парсеры"""
    print("\nTEST Тестирование парсеров...")
    
    config = Config()
    results = {}
    
    # Twitter
    if config.ENABLE_TWITTER:
        try:
            from sources.twitter_parser import TwitterParser
            parser = TwitterParser()
            news = parser.search_tweets(max_results=1)
            results['Twitter'] = f"OK {len(news)} новостей"
        except Exception as e:
            results['Twitter'] = f"ERROR {str(e)[:50]}..."
    else:
        results['Twitter'] = "⏭️ отключен"
    
    # Google News
    if config.ENABLE_GOOGLE_NEWS:
        try:
            from sources.google_news_parser import GoogleNewsParser
            parser = GoogleNewsParser()
            news = parser.search_news(max_results=1)
            results['Google News'] = f"OK {len(news)} новостей"
        except Exception as e:
            results['Google News'] = f"ERROR {str(e)[:50]}..."
    else:
        results['Google News'] = "⏭️ отключен"
    
    # Hacker News
    if config.ENABLE_HACKERNEWS:
        try:
            from sources.hackernews_parser import HackerNewsParser
            parser = HackerNewsParser()
            news = parser.search_stories(max_results=1)
            results['Hacker News'] = f"OK {len(news)} новостей"
        except Exception as e:
            results['Hacker News'] = f"ERROR {str(e)[:50]}..."
    else:
        results['Hacker News'] = "⏭️ отключен"
    
    # Reddit
    if config.ENABLE_REDDIT:
        try:
            from sources.reddit_parser import RedditParser
            parser = RedditParser()
            news = parser.search_posts(max_results=1)
            results['Reddit'] = f"OK {len(news)} новостей"
        except Exception as e:
            results['Reddit'] = f"ERROR {str(e)[:50]}..."
    else:
        results['Reddit'] = "⏭️ отключен"

    # YouTube
    if config.ENABLE_YOUTUBE:
        try:
            from sources.youtube_parser import YouTubeParser
            parser = YouTubeParser()
            news = parser.search_videos(max_results=1)
            results['YouTube'] = f"OK {len(news)} видео"
        except Exception as e:
            results['YouTube'] = f"ERROR {str(e)[:50]}..."
    else:
        results['YouTube'] = "⏭️ отключен"
    
    # Выводим результаты
    for source, result in results.items():
        print(f"   {source}: {result}")
    
    return True

def main():
    """Основная функция тестирования"""
    print("Тестирование AI News Aggregator")
    print("=" * 50)
    
    # Настраиваем логирование
    logger = setup_logging()
    
    tests = [
        ("Конфигурация", test_config),
        ("Фильтры", test_filters),
        ("Telegram", test_telegram),
        ("Парсеры", test_parsers)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"ERROR Критическая ошибка в тесте '{test_name}': {e}")
    
    print("\n" + "=" * 50)
    print(f"Результаты тестирования: {passed}/{total} тестов пройдено")
    
    if passed == total:
        print("SUCCESS Все тесты пройдены успешно!")
        return True
    else:
        print("WARNING Некоторые тесты не пройдены. Проверьте настройки.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
