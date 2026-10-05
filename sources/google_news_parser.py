import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Sequence
import feedparser
from urllib.parse import quote_plus
from utils.config import Config
from utils.filters import NewsFilter


class GoogleNewsParser:
    """Парсер Google News RSS по active-ключевым словам из базы."""

    def __init__(self, active_keywords: Optional[Sequence[str]] = None):
        self.config = Config()
        self.filter = NewsFilter(active_keywords)
        self.logger = logging.getLogger(__name__)

    def set_active_keywords(self, keywords: Sequence[str]) -> None:
        self.filter.set_active_keywords(keywords)

    def search_news(self, max_results: int = 60) -> List[Dict[str, Any]]:
        news_items: List[Dict[str, Any]] = []
        keywords = list(self.filter.active_keywords)
        if not keywords:
            self.logger.warning("Google News: нет active-ключевых слов")
            return []

        per_keyword = max(2, max_results // max(min(len(keywords), 20), 1))
        for keyword in keywords[:25]:
            try:
                keyword_news = self._search_by_keyword(keyword, per_keyword)
                news_items.extend(keyword_news)
                self.logger.info("Google News '%s': %s", keyword, len(keyword_news))
            except Exception as e:
                self.logger.error("Ошибка Google News '%s': %s", keyword, e)

        news_items = self.filter.remove_duplicates(news_items)
        return news_items[:max_results]

    def _search_by_keyword(self, keyword: str, max_results: int = 10) -> List[Dict[str, Any]]:
        news_items = []
        if any("а" <= ch <= "я" or ch == "ё" for ch in keyword.lower()):
            feeds = [("ru", "RU", "RU")]
        else:
            feeds = [("en", region, region) for region in ("US", "GB", "CA", "AU")]

        for hl, gl, ceid in feeds:
            try:
                encoded_keyword = quote_plus(keyword)
                rss_url = (
                    f"https://news.google.com/rss/search?q={encoded_keyword}"
                    f"&hl={hl}-{gl}&gl={gl}&ceid={ceid}:{hl}"
                )
                feed = feedparser.parse(rss_url)
                if feed.bozo:
                    self.logger.warning("RSS ошибки %s: %s", gl, feed.bozo_exception)
                    continue
                count = 0
                for entry in feed.entries:
                    if count >= max_results:
                        break
                    news_data = self._extract_news_data(entry)
                    if news_data and self._is_valid_news(news_data):
                        news_items.append(news_data)
                        count += 1
            except Exception as e:
                self.logger.error("Ошибка региона %s: %s", gl, e)
        return news_items

    def _extract_news_data(self, entry) -> Dict[str, Any]:
        try:
            from datetime import timezone

            published_date = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published_date = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                published_date = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)

            if not self.filter.is_recent_news(published_date, self.config.NEWS_LOOKBACK_DAYS * 24):
                return None

            source = self._extract_source(entry.link) if hasattr(entry, "link") else "Unknown"
            title = entry.title if hasattr(entry, "title") else ""
            summary = entry.summary if hasattr(entry, "summary") else ""
            return {
                "title": title,
                "url": entry.link if hasattr(entry, "link") else "",
                "source": source,
                "published_date": published_date,
                "description": summary,
                "keywords": self.filter.extract_keywords_from_text(title + " " + summary),
            }
        except Exception as e:
            self.logger.error("Ошибка извлечения новости: %s", e)
            return None

    def _extract_source(self, url: str) -> str:
        try:
            if not url:
                return "Unknown"
            url = url.replace("https://", "").replace("http://", "").replace("www.", "")
            domain = url.split("/")[0]
            known = {
                "cnn.com": "CNN",
                "bbc.com": "BBC",
                "reuters.com": "Reuters",
                "techcrunch.com": "TechCrunch",
                "theverge.com": "The Verge",
                "wired.com": "Wired",
            }
            for key, name in known.items():
                if key in domain:
                    return name
            return domain.split(".")[0].title()
        except Exception:
            return "Unknown"

    def _is_valid_news(self, news_data: Dict[str, Any]) -> bool:
        if not news_data:
            return False
        title = news_data.get("title", "")
        description = news_data.get("description", "")
        if not self.filter.contains_ai_keywords(title + " " + description):
            return False
        if len(title) < 10:
            return False
        return True
