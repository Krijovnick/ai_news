import re
from datetime import datetime, timedelta
from typing import List, Dict, Any
from utils.config import Config

class NewsFilter:
    """Класс для фильтрации новостей"""
    
    def __init__(self):
        self.config = Config()
    
    def is_recent_news(self, published_date: datetime, hours: int = 24) -> bool:
        """Проверяет, является ли новость свежей (за последние N часов)"""
        if not published_date:
            return False
        
        from datetime import timezone
        now = datetime.now(timezone.utc)
        cutoff_time = now - timedelta(hours=hours)
        
        if published_date.tzinfo is None:
            published_date = published_date.replace(tzinfo=timezone.utc)
        
        return published_date >= cutoff_time
    
    def contains_ai_keywords(self, text: str) -> bool:
        """Проверяет, содержит ли текст ключевые слова об ИИ"""
        if not text:
            return False
        
        text_lower = text.lower()
        
        has_ai_keywords = any(keyword.lower() in text_lower for keyword in self.config.AI_KEYWORDS)
        
        has_exclude_keywords = any(keyword.lower() in text_lower for keyword in self.config.EXCLUDE_KEYWORDS)
        
        return has_ai_keywords and not has_exclude_keywords
    
    def is_retweet(self, text: str) -> bool:
        """Проверяет, является ли твит ретвитом"""
        return text.startswith('RT @') or text.startswith('rt @')
    
    def clean_text(self, text: str) -> str:
        """Очищает текст от лишних символов"""
        if not text:
            return ""
        
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()
        
        return text
    
    def extract_keywords_from_text(self, text: str) -> List[str]:
        """Извлекает ключевые слова из текста"""
        if not text:
            return []
        
        text_lower = text.lower()
        found_keywords = []
        
        for keyword in self.config.AI_KEYWORDS:
            if keyword.lower() in text_lower:
                found_keywords.append(keyword)
        
        return found_keywords
    
    def is_english_or_russian(self, text: str) -> bool:
        """Проверяет, является ли текст на английском или русском языке"""
        if not text:
            return False
        
        cyrillic_count = len(re.findall(r'[а-яё]', text.lower()))
        latin_count = len(re.findall(r'[a-z]', text.lower()))
        
        unwanted_chars = len(re.findall(r'[^\w\s\-.,!?()\[\]":;@#$%^&*+=<>/\\|`~]', text))
        
        total_letters = cyrillic_count + latin_count
        total_chars = len(re.findall(r'[^\s]', text))  # Все не-пробельные символы
        
        if total_letters == 0:
            return False
        
        if unwanted_chars > 0:
            return False
        
        cyrillic_ratio = cyrillic_count / total_letters
        latin_ratio = latin_count / total_letters
        
        return total_letters >= 3 and (cyrillic_ratio > 0.8 or latin_ratio > 0.8)
    
    def calculate_relevance_score(self, title: str, description: str = "", keywords: List[str] = None) -> int:
        """Вычисляет релевантность новости (0-100)"""
        if not title:
            return 0
        
        score = 0
        text = f"{title} {description}".lower()
        
        high_priority = ["chatgpt", "openai", "claude", "gemini", "sora", "gpt-4", "gpt-5"]
        for keyword in high_priority:
            if keyword in text:
                score += 20
        
        medium_priority = ["ai", "artificial intelligence", "stable diffusion", "midjourney"]
        for keyword in medium_priority:
            if keyword in text:
                score += 10
        
        low_priority = ["machine learning", "deep learning", "neural network"]
        for keyword in low_priority:
            if keyword in text:
                score += 5
        
        if keywords:
            score += min(len(keywords) * 5, 20)
        
        return min(score, 100)
    
    def filter_news_by_relevance(self, news_list: List[Dict[str, Any]], min_score: int = 30) -> List[Dict[str, Any]]:
        """Фильтрует новости по релевантности и языку"""
        filtered_news = []
        
        for news in news_list:
            title = news.get('title', '')
            description = news.get('description', '')
            keywords = news.get('keywords', [])
            
            if not self.is_english_or_russian(title):
                continue
            
            score = self.calculate_relevance_score(title, description, keywords)
            
            if score >= min_score:
                news['relevance_score'] = score
                news['popularity_score'] = self.calculate_popularity_score(news)
                news['ranking_score'] = score * 0.6 + news['popularity_score'] * 0.4
                filtered_news.append(news)
        
        filtered_news.sort(key=lambda x: x.get('ranking_score', 0), reverse=True)
        
        return filtered_news

    def calculate_popularity_score(self, news: Dict[str, Any]) -> int:
        """Единая оценка популярности контента (0-100) для разных источников."""
        if not news:
            return 0

        popularity = 0.0
        popularity += float(news.get("view_count", 0)) / 2000.0
        popularity += float(news.get("like_count", 0)) / 150.0
        popularity += float(news.get("retweet_count", 0)) / 80.0
        popularity += float(news.get("reply_count", 0)) / 80.0
        popularity += float(news.get("score", 0)) / 8.0
        popularity += float(news.get("comments_count", 0)) / 20.0

        return int(min(popularity, 100))

    def filter_business_reddit_posts(
        self,
        posts: List[Dict[str, Any]],
        max_items: int = 50,
    ) -> List[Dict[str, Any]]:
        """Язык + сортировка по Reddit score (популярность), без ИИ-релевантности."""
        out: List[Dict[str, Any]] = []
        for post in posts:
            title = post.get("title", "")
            if not self.is_english_or_russian(title):
                continue
            out.append(post)
        out.sort(key=lambda x: x.get("score", 0), reverse=True)
        return out[:max_items]

    def remove_duplicates(self, news_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Удаляет дубликаты новостей"""
        seen_titles = set()
        seen_urls = set()
        unique_news = []
        
        for news in news_list:
            title = news.get('title', '').lower().strip()
            url = news.get('url', '')
            
            # Проверяем дубликаты по заголовку и URL
            if title not in seen_titles and url not in seen_urls:
                seen_titles.add(title)
                seen_urls.add(url)
                unique_news.append(news)
        
        return unique_news
    
    def format_news_for_telegram(self, news_list: List[Dict[str, Any]], max_items: int = 20) -> str:
        """Форматирует новости для отправки в Telegram"""
        if not news_list:
            return f"📰 *AI News Digest*\n\nНовостей не найдено за последние {self.config.NEWS_LOOKBACK_DAYS} дней."
        
        # Ограничиваем количество новостей
        news_list = news_list[:max_items]
        
        # Получаем текущую дату
        from datetime import timezone
        current_date = datetime.now(timezone.utc).strftime("%d %B %Y")
        
        # Формируем заголовок
        header = f"📰 <b>AI News Digest — {current_date}</b>\n\n"
        
        # Формируем список новостей
        news_items = []
        for i, news in enumerate(news_list, 1):
            title = news.get('title', 'Без заголовка')
            url = news.get('url', '#')
            source = news.get('source', 'Неизвестный источник')
            content_type = news.get('content_type', '')
            duration = news.get('duration', 0)
            
            # Не обрезаем заголовки - показываем полные названия
            
            # Добавляем эмодзи для типа контента Reddit
            content_emoji = ""
            if 'Reddit' in source and content_type:
                emoji_map = {
                    'image': '🖼️',
                    'video': '🎥', 
                    'text': '📝',
                    'link': '🔗'
                }
                content_emoji = emoji_map.get(content_type, '📄')
                        
            # Формируем строку с учетом типа контента
            if content_emoji:
                news_item = f"🔹 {content_emoji} <a href='{url}'>{title}</a>\nИсточник: {source}"
            else:
                news_item = f"🔹 <a href='{url}'>{title}</a>\nИсточник: {source}"
            
            news_items.append(news_item)
        
        return header + "\n".join(news_items)
