import math
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Sequence
from utils.config import Config


class NewsFilter:
    """Класс для фильтрации новостей"""

    def __init__(self, active_keywords: Optional[Sequence[str]] = None):
        self.config = Config()
        self.active_keywords: List[str] = list(active_keywords) if active_keywords is not None else []

    def set_active_keywords(self, keywords: Sequence[str]) -> None:
        self.active_keywords = list(keywords)

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

    def has_exclude_keywords(self, text: str) -> bool:
        if not text:
            return False
        text_lower = text.lower()
        return any(keyword.lower() in text_lower for keyword in self.config.EXCLUDE_KEYWORDS)

    def matches_active_keywords(self, text: str) -> bool:
        if not text or not self.active_keywords:
            return False
        text_lower = text.lower()
        for keyword in self.active_keywords:
            kw = keyword.lower()
            if len(kw) <= 3:
                if re.search(rf"(?<!\w){re.escape(kw)}(?!\w)", text_lower, flags=re.UNICODE):
                    return True
            elif kw in text_lower:
                return True
        return False

    def has_explicit_ai_sense(self, text: str) -> bool:
        if not text:
            return False
        text_lower = text.lower()
        for marker in self.config.AI_SENSE_MARKERS:
            m = marker.lower()
            # Короткие маркеры — только как отдельное слово (не «said» / «email»)
            if len(m) <= 3:
                if re.search(rf"(?<!\w){re.escape(m)}(?!\w)", text_lower, flags=re.UNICODE):
                    return True
            elif m in text_lower:
                return True
        return False

    def contains_ai_keywords(self, text: str) -> bool:
        """Есть active-ключевое слово (или явный ИИ-смысл) и нет exclude."""
        if not text:
            return False
        if self.has_exclude_keywords(text):
            return False
        return self.matches_active_keywords(text) or self.has_explicit_ai_sense(text)

    def clean_text(self, text: str) -> str:
        if not text:
            return ""
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def extract_keywords_from_text(self, text: str) -> List[str]:
        if not text or not self.active_keywords:
            return []
        text_lower = text.lower()
        found = []
        for keyword in self.active_keywords:
            if keyword.lower() in text_lower:
                found.append(keyword)
        return found

    def is_english_or_russian(self, text: str) -> bool:
        if not text:
            return False

        cyrillic_count = len(re.findall(r"[а-яё]", text.lower()))
        latin_count = len(re.findall(r"[a-z]", text.lower()))
        unwanted_chars = len(re.findall(r'[^\w\s\-.,!?()\[\]":;@#$%^&*+=<>/\\|`~]', text))
        total_letters = cyrillic_count + latin_count

        if total_letters == 0:
            return False
        if unwanted_chars > 0:
            return False

        cyrillic_ratio = cyrillic_count / total_letters
        latin_ratio = latin_count / total_letters
        return total_letters >= 3 and (cyrillic_ratio > 0.8 or latin_ratio > 0.8)

    def title_letters_are_ru_or_en(self, text: str) -> bool:
        """Русский или английский по буквам. Пунктуация заголовок не отбрасывает.

        Доля кириллицы или латиницы считается среди всех букв, не меньше 3.
        Одна из долей должна быть больше 0.8. Для собранных новостей по-прежнему
        используется is_english_or_russian.
        """
        if not text:
            return False
        letters = [ch for ch in text if ch.isalpha()]
        total = len(letters)
        if total < 3:
            return False
        cyrillic = 0
        latin = 0
        for ch in letters:
            lower = ch.lower()
            if ("а" <= lower <= "я") or lower == "ё":
                cyrillic += 1
            elif "a" <= lower <= "z":
                latin += 1
        return (cyrillic / total > 0.8) or (latin / total > 0.8)

    def calculate_relevance_score(self, title: str, description: str = "", keywords: List[str] = None) -> int:
        if not title:
            return 0

        score = 0
        text = f"{title} {description}".lower()

        high_priority = [
            "ai agent",
            "ai agents",
            "autonomous agent",
            "multi-agent",
            "ai automation",
            "business automation",
            "workflow automation",
            "n8n",
            "zapier",
            "make.com",
            "ai saas",
            "micro saas",
            "ai for business",
            "ai for sales",
            "ai for marketing",
            "claude code",
            "cursor ai",
            "coding agent",
            "agent framework",
            "developer tool",
            "open source ai",
            "new ai tool",
            "new ai agent",
            "emerging ai",
            "ai agent setup",
            "configuring ai agents",
            "ии агент",
            "автоматизация бизнеса",
            "ии для бизнеса",
            "настройка ии агент",
            "новые ии инструмент",
        ]
        for keyword in high_priority:
            if keyword in text:
                score += 22

        medium_priority = [
            "automation",
            "workflow",
            "use case",
            "startup",
            "saas",
            "productivity",
            "no-code",
            "nocode",
            "indie hacker",
            "build with ai",
            "chatgpt",
            "claude",
            "openai",
            "tutorial",
            "how to",
            "playbook",
            "case study",
            "framework",
            "open source",
            "open-source",
            "developer tool",
            "автоматиз",
            "стартап",
            "заработ",
            "кейс",
            "новый инструмент",
        ]
        for keyword in medium_priority:
            if keyword in text:
                score += 10

        low_priority = ["artificial intelligence", "generative ai", "llm", "gpt-4", "gpt-5", "gemini"]
        for keyword in low_priority:
            if keyword in text:
                score += 4

        practical_hits = sum(1 for kw in self.config.PRACTICAL_KEYWORDS if kw.lower() in text)
        score += min(practical_hits * 6, 30)

        if keywords:
            score += min(len(keywords) * 4, 16)

        for phrase in self.config.ANNOUNCEMENT_PENALTY_KEYWORDS:
            if phrase.lower() in text:
                score -= 28
                break

        return max(0, min(score, 100))

    def filter_news_by_relevance(self, news_list: List[Dict[str, Any]], min_score: int = 30) -> List[Dict[str, Any]]:
        filtered_news = []

        for news in news_list:
            title = news.get("title", "")
            description = news.get("description", "")
            keywords = news.get("keywords", [])

            if not self.is_english_or_russian(title):
                continue

            score = self.calculate_relevance_score(title, description, keywords)

            if score >= min_score:
                news["relevance_score"] = score
                news["popularity_score"] = self.calculate_popularity_score(news)
                news["ranking_score"] = score * 0.7 + news["popularity_score"] * 0.3
                filtered_news.append(news)

        filtered_news.sort(key=lambda x: x.get("ranking_score", 0), reverse=True)
        return filtered_news

    def calculate_popularity_score(self, news: Dict[str, Any]) -> int:
        if not news:
            return 0

        popularity = 0.0
        views = float(news.get("view_count", 0) or 0)
        likes = float(news.get("like_count", 0) or 0)
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
        if "r/" in source:
            return source.split("r/", 1)[-1].strip()
        return (post.get("subreddit") or "").lower()

    def is_offline_business_post(self, post: Dict[str, Any]) -> bool:
        text = self._business_post_text(post)
        return any(kw.lower() in text for kw in self.config.REDDIT_OFFLINE_KEYWORDS)

    def is_online_ai_business_post(self, post: Dict[str, Any]) -> bool:
        """Онлайн-бизнес про ИИ: без спама/офлайна, с ИИ-смыслом или active-ключом."""
        text = self._business_post_text(post)
        if not text.strip():
            return False

        excludes = getattr(self.config, "REDDIT_BUSINESS_EXCLUDE_KEYWORDS", []) or []
        if any(kw.lower() in text for kw in excludes):
            return False
        if self.is_offline_business_post(post):
            return False
        if self.has_exclude_keywords(text):
            return False

        return self.matches_active_keywords(text) or self.has_explicit_ai_sense(text)

    def _title_words(self, title: str) -> List[str]:
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
        if shared >= 6:
            return True
        return shared >= 4 and shorter > 0 and shared / shorter >= 0.65

    def titles_look_similar(self, left_title: str, right_title: str) -> bool:
        left = self._title_words(left_title)
        right = self._title_words(right_title)
        if not left or not right:
            return False
        shorter = min(len(left), len(right))
        prefix = self._shared_edge_len(left, right)
        suffix = self._shared_edge_len(list(reversed(left)), list(reversed(right)))
        return self._edge_is_similar(prefix, shorter) or self._edge_is_similar(suffix, shorter)

    def drop_similar_titles(self, news_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        kept: List[Dict[str, Any]] = []
        for news in news_list:
            title = news.get("title", "")
            if any(self.titles_look_similar(title, prev.get("title", "")) for prev in kept):
                continue
            kept.append(news)
        return kept

    def remove_duplicates(self, news_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen_titles = set()
        seen_urls = set()
        unique_news = []

        for news in news_list:
            title = news.get("title", "").lower().strip()
            url = news.get("url") or ""
            if not isinstance(url, str):
                url = str(url)
            # Пустой URL — не адрес: им нельзя схлопывать разные заголовки.
            same_url = bool(url.strip()) and url in seen_urls
            if title not in seen_titles and not same_url:
                seen_titles.add(title)
                if url.strip():
                    seen_urls.add(url)
                unique_news.append(news)
        return unique_news


def build_run_ready_notification(web_url: Optional[str] = None) -> str:
    """Одно уведомление после успешного прогона: без списка новостей."""
    url = web_url or Config.WEB_URL
    return (
        f"✅ Разбор недели готов.\n"
        f"Смотреть на {url}"
    )
