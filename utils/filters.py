import math
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

    def matches_discovery(self, text: str) -> bool:
        """Новый инструмент, фреймворк или способ автоматизации — без привязки к известному продукту."""
        if not text:
            return False
        text_lower = text.lower()
        keywords = getattr(self.config, "DISCOVERY_KEYWORDS", []) or []
        return any(keyword.lower() in text_lower for keyword in keywords)
    
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
        """Релевантность: приоритет практике (агенты, автоматизация, бизнес), не анонсам."""
        if not title:
            return 0

        score = 0
        text = f"{title} {description}".lower()

        # Высокий приоритет — то, что можно внедрить и монетизировать
        high_priority = [
            "ai agent", "ai agents", "autonomous agent", "multi-agent",
            "ai automation", "business automation", "workflow automation",
            "n8n", "zapier", "make.com", "ai saas", "micro saas",
            "ai for business", "ai for sales", "ai for marketing",
            "claude code", "cursor ai", "coding agent",
            "agent framework", "developer tool", "open source ai",
            "new ai tool", "new ai agent", "emerging ai",
            "ai agent setup", "configuring ai agents",
            "ии агент", "автоматизация бизнеса", "ии для бизнеса",
            "настройка ии агент", "новые ии инструмент",
        ]
        for keyword in high_priority:
            if keyword in text:
                score += 22

        medium_priority = [
            "automation", "workflow", "use case", "startup", "saas",
            "productivity", "no-code", "nocode", "indie hacker",
            "build with ai", "chatgpt", "claude", "openai",
            "tutorial", "how to", "playbook", "case study",
            "framework", "open source", "open-source", "developer tool",
            "автоматиз", "стартап", "заработ", "кейс", "новый инструмент",
        ]
        for keyword in medium_priority:
            if keyword in text:
                score += 10

        # Слабый сигнал — общий ИИ без прикладного контекста
        low_priority = ["artificial intelligence", "generative ai", "llm", "gpt-4", "gpt-5", "gemini"]
        for keyword in low_priority:
            if keyword in text:
                score += 4

        # Доп. буст за явные practical-сигналы из конфига
        practical_hits = sum(
            1 for kw in self.config.PRACTICAL_KEYWORDS if kw.lower() in text
        )
        score += min(practical_hits * 6, 30)

        if keywords:
            score += min(len(keywords) * 4, 16)

        # Штраф за «просто анонс релиза»
        for phrase in self.config.ANNOUNCEMENT_PENALTY_KEYWORDS:
            if phrase.lower() in text:
                score -= 28
                break

        return max(0, min(score, 100))

    
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
                news['ranking_score'] = score * 0.7 + news['popularity_score'] * 0.3
                filtered_news.append(news)
        
        filtered_news.sort(key=lambda x: x.get('ranking_score', 0), reverse=True)
        
        return filtered_news

    def calculate_popularity_score(self, news: Dict[str, Any]) -> int:
        """Единая оценка популярности контента (0-100) для разных источников."""
        if not news:
            return 0

        popularity = 0.0

        views = float(news.get("view_count", 0) or 0)
        likes = float(news.get("like_count", 0) or 0)
        # Логарифм, чтобы 100k и 2M просмотров различались (линейный /2000 всё режет в 100)
        if views > 0:
            popularity += min(math.log10(views) * 22, 70)
        if likes > 0:
            popularity += min(math.log10(likes) * 12, 25)

        popularity += float(news.get("retweet_count", 0) or 0) / 80.0
        popularity += float(news.get("reply_count", 0) or 0) / 80.0
        popularity += float(news.get("score", 0) or 0) / 8.0
        popularity += float(news.get("comments_count", 0) or 0) / 20.0

        return int(min(popularity, 100))

    def _business_post_text(self, post: Dict[str, Any]) -> str:
        title = post.get("title") or ""
        description = post.get("description") or ""
        return f"{title}\n{description}".lower()

    def _business_subreddit_slug(self, post: Dict[str, Any]) -> str:
        source = (post.get("source") or "").lower()
        # "Reddit r/startup_ideas" → "startup_ideas"
        if "r/" in source:
            return source.split("r/", 1)[-1].strip()
        return ""

    def is_business_idea_post(self, post: Dict[str, Any]) -> bool:
        """
        Идеи бизнеса, истории запуска, решаемые проблемы — не общая бизнес-пресса.
        В idea-сабах достаточно отсутствия exclude-спама.
        """
        text = self._business_post_text(post)
        if not text.strip():
            return False

        excludes = getattr(self.config, "REDDIT_BUSINESS_EXCLUDE_KEYWORDS", []) or []
        if any(kw.lower() in text for kw in excludes):
            return False

        sub = self._business_subreddit_slug(post)
        idea_subs = {
            s.lower() for s in (getattr(self.config, "REDDIT_BUSINESS_IDEA_SUBREDDITS", set()) or set())
        }
        if sub in idea_subs:
            return True

        keywords = getattr(self.config, "REDDIT_BUSINESS_IDEA_KEYWORDS", []) or []
        return any(kw.lower() in text for kw in keywords)

    def business_idea_relevance(self, post: Dict[str, Any]) -> int:
        """Сколько idea-ключевых слов совпало (+бонус за idea-саб)."""
        text = self._business_post_text(post)
        keywords = getattr(self.config, "REDDIT_BUSINESS_IDEA_KEYWORDS", []) or []
        hits = sum(1 for kw in keywords if kw.lower() in text)
        sub = self._business_subreddit_slug(post)
        idea_subs = {
            s.lower() for s in (getattr(self.config, "REDDIT_BUSINESS_IDEA_SUBREDDITS", set()) or set())
        }
        if sub in idea_subs:
            hits += 2
        return hits

    def filter_business_reddit_posts(
        self,
        posts: List[Dict[str, Any]],
        max_items: int = 50,
    ) -> List[Dict[str, Any]]:
        """Идеи/истории + язык; сортировка: релевантность идее, затем Reddit score."""
        out: List[Dict[str, Any]] = []
        for post in posts:
            title = post.get("title", "")
            if not self.is_english_or_russian(title):
                continue
            if not self.is_business_idea_post(post):
                continue
            out.append(post)
        out.sort(
            key=lambda x: (self.business_idea_relevance(x), x.get("score", 0)),
            reverse=True,
        )
        return out[:max_items]

    def _title_words(self, title: str) -> List[str]:
        """Слова заголовка без пунктуации — для сравнения начала и конца."""
        text = re.sub(r"[^\w\s]", " ", (title or "").lower(), flags=re.UNICODE)
        return [word for word in text.split() if word]

    def _shared_edge_len(self, left: List[str], right: List[str]) -> int:
        shared = 0
        for left_word, right_word in zip(left, right):
            if left_word != right_word:
                break
            shared += 1
        return shared

    def _edge_is_similar(self, shared: int, shorter: int) -> bool:
        """Совпадает длинный кусок, либо короче заголовок почти целиком с края."""
        if shared >= 6:
            return True
        return shared >= 4 and shorter > 0 and shared / shorter >= 0.65

    def titles_look_similar(self, left_title: str, right_title: str) -> bool:
        """Похожи, если совпадает начало или конец, а середина может отличаться."""
        left = self._title_words(left_title)
        right = self._title_words(right_title)
        if not left or not right:
            return False
        shorter = min(len(left), len(right))
        prefix = self._shared_edge_len(left, right)
        suffix = self._shared_edge_len(list(reversed(left)), list(reversed(right)))
        return self._edge_is_similar(prefix, shorter) or self._edge_is_similar(suffix, shorter)

    def drop_similar_titles(self, news_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Убирает похожие заголовки. Список должен быть отсортирован: выше рейтинг — раньше."""
        kept: List[Dict[str, Any]] = []
        for news in news_list:
            title = news.get("title", "")
            if any(self.titles_look_similar(title, prev.get("title", "")) for prev in kept):
                continue
            kept.append(news)
        return kept

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
