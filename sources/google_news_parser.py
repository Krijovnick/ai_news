import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any
import feedparser
import requests
from urllib.parse import quote_plus
from utils.config import Config
from utils.filters import NewsFilter

class GoogleNewsParser:
    """Парсер для Google News с использованием RSS фидов"""
    
    def __init__(self):
        self.config = Config()
        self.filter = NewsFilter()
        self.logger = logging.getLogger(__name__)
    
    def search_news(self, max_results: int = 50) -> List[Dict[str, Any]]:
        """Поиск новостей по ключевым словам"""
        news_items = []
        
        try:
            # Поиск по каждому ключевому слову
            for keyword in self.config.AI_KEYWORDS[:8]:  # Ограничиваем количество запросов
                try:
                    keyword_news = self._search_by_keyword(keyword, max_results // len(self.config.AI_KEYWORDS[:8]))
                    news_items.extend(keyword_news)
                    
                    self.logger.info(f"Найдено {len(keyword_news)} новостей для ключевого слова: {keyword}")
                    
                except Exception as e:
                    self.logger.error(f"Ошибка при поиске новостей для '{keyword}': {e}")
                    continue
            
            # Удаляем дубликаты
            news_items = self.filter.remove_duplicates(news_items)
            
            self.logger.info(f"Всего найдено уникальных новостей: {len(news_items)}")
            return news_items
            
        except Exception as e:
            self.logger.error(f"Ошибка при поиске новостей: {e}")
            return []
    
    def _search_by_keyword(self, keyword: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """Поиск новостей по конкретному ключевому слову"""
        news_items = []
        
        try:
            # Формируем URL для RSS фида Google News
            # Используем разные регионы для получения большего количества новостей
            regions = ['US', 'GB', 'CA', 'AU']
            
            for region in regions:
                try:
                    # URL для RSS фида Google News (кодируем ключевое слово)
                    encoded_keyword = quote_plus(keyword)
                    rss_url = f"https://news.google.com/rss/search?q={encoded_keyword}&hl=en-{region}&gl={region}&ceid={region}:en"
                    
                    # Парсим RSS фид
                    feed = feedparser.parse(rss_url)
                    
                    if feed.bozo:
                        self.logger.warning(f"RSS фид содержит ошибки для региона {region}: {feed.bozo_exception}")
                        continue
                    
                    count = 0
                    for entry in feed.entries:
                        if count >= max_results:
                            break
                        
                        news_data = self._extract_news_data(entry)
                        if news_data and self._is_valid_news(news_data):
                            news_items.append(news_data)
                            count += 1
                    
                    self.logger.info(f"Найдено {count} новостей для региона {region}")
                    
                except Exception as e:
                    self.logger.error(f"Ошибка при парсинге RSS для региона {region}: {e}")
                    continue
            
            return news_items
            
        except Exception as e:
            self.logger.error(f"Ошибка при поиске новостей по ключевому слову '{keyword}': {e}")
            return []
    
    def _extract_news_data(self, entry) -> Dict[str, Any]:
        """Извлекает данные о новости из RSS записи"""
        try:
            # Парсим дату публикации с UTC часовым поясом
            from datetime import timezone
            published_date = None
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                published_date = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                published_date = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
            
            # Проверяем, что новость свежая (за последние 24 часа)
            if not self.filter.is_recent_news(published_date, 24):
                return None
            
            # Извлекаем источник из ссылки или заголовка
            source = self._extract_source(entry.link) if hasattr(entry, 'link') else 'Unknown'
            
            news_data = {
                'title': entry.title if hasattr(entry, 'title') else '',
                'url': entry.link if hasattr(entry, 'link') else '',
                'source': source,
                'published_date': published_date,
                'description': entry.summary if hasattr(entry, 'summary') else '',
                'keywords': self.filter.extract_keywords_from_text(
                    (entry.title if hasattr(entry, 'title') else '') + 
                    ' ' + (entry.summary if hasattr(entry, 'summary') else '')
                )
            }
            
            return news_data
            
        except Exception as e:
            self.logger.error(f"Ошибка при извлечении данных новости: {e}")
            return None
    
    def _extract_source(self, url: str) -> str:
        """Извлекает название источника из URL"""
        try:
            if not url:
                return 'Unknown'
            
            # Удаляем протокол и www
            url = url.replace('https://', '').replace('http://', '').replace('www.', '')
            
            # Извлекаем домен
            domain = url.split('/')[0]
            
            # Убираем поддомены для известных источников
            known_sources = {
                'cnn.com': 'CNN',
                'bbc.com': 'BBC',
                'reuters.com': 'Reuters',
                'ap.org': 'Associated Press',
                'bloomberg.com': 'Bloomberg',
                'techcrunch.com': 'TechCrunch',
                'theverge.com': 'The Verge',
                'wired.com': 'Wired',
                'arstechnica.com': 'Ars Technica',
                'engadget.com': 'Engadget'
            }
            
            for domain_key, source_name in known_sources.items():
                if domain_key in domain:
                    return source_name
            
            # Если источник не известен, возвращаем домен
            return domain.split('.')[0].title()
            
        except Exception as e:
            self.logger.error(f"Ошибка при извлечении источника из URL: {e}")
            return 'Unknown'
    
    def _is_valid_news(self, news_data: Dict[str, Any]) -> bool:
        """Проверяет, подходит ли новость для включения в дайджест"""
        if not news_data:
            return False
        
        title = news_data.get('title', '')
        description = news_data.get('description', '')
        
        # Проверяем наличие ключевых слов
        if not self.filter.contains_ai_keywords(title + ' ' + description):
            return False
        
        # Проверяем минимальную длину заголовка
        if len(title) < 10:
            return False
        
        return True
    
    def get_trending_news(self, max_results: int = 30) -> List[Dict[str, Any]]:
        """Получает трендовые новости по теме ИИ"""
        news_items = []
        
        try:
            # URL для трендовых новостей Google News
            rss_url = "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en"
            
            feed = feedparser.parse(rss_url)
            
            if feed.bozo:
                self.logger.warning(f"RSS фид содержит ошибки: {feed.bozo_exception}")
                return []
            
            count = 0
            for entry in feed.entries:
                if count >= max_results:
                    break
                
                news_data = self._extract_news_data(entry)
                if news_data and self._is_valid_news(news_data):
                    news_items.append(news_data)
                    count += 1
            
            self.logger.info(f"Найдено {len(news_items)} трендовых новостей")
            return news_items
            
        except Exception as e:
            self.logger.error(f"Ошибка при получении трендовых новостей: {e}")
            return []
