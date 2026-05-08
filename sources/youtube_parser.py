import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
import requests

from utils.config import Config
from utils.filters import NewsFilter


class YouTubeParser:
    """Парсер топовых видео YouTube через Data API v3."""

    def __init__(self):
        self.config = Config()
        self.filter = NewsFilter()
        self.logger = logging.getLogger(__name__)
        self.base_url = "https://www.googleapis.com/youtube/v3"

        if not self.config.YOUTUBE_API_KEY:
            raise ValueError("YOUTUBE_API_KEY не установлен")

    def search_videos(self, max_results: int = 40) -> List[Dict[str, Any]]:
        """Ищет популярные видео об ИИ за последние N дней."""
        videos: List[Dict[str, Any]] = []

        try:
            days = self.config.NEWS_LOOKBACK_DAYS
            published_after = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat().replace("+00:00", "Z")

            per_query_limit = max(5, min(self.config.YOUTUBE_MAX_RESULTS_PER_QUERY, max_results))
            keywords = self.config.AI_KEYWORDS

            for keyword in keywords:
                ids = self._search_video_ids(keyword, published_after, per_query_limit)
                if not ids:
                    continue

                details = self._fetch_video_details(ids)
                for video in details:
                    if self._is_valid_video(video):
                        videos.append(video)

            videos = self.filter.remove_duplicates(videos)
            videos.sort(
                key=lambda x: (
                    x.get("view_count", 0),
                    x.get("like_count", 0),
                    x.get("comments_count", 0),
                ),
                reverse=True,
            )

            return videos[:max_results]
        except Exception as e:
            self.logger.error("Ошибка при поиске YouTube видео: %s", e)
            return []

    def _search_video_ids(self, keyword: str, published_after: str, max_results: int) -> List[str]:
        params = {
            "part": "snippet",
            "q": keyword,
            "type": "video",
            "order": "viewCount",
            "publishedAfter": published_after,
            "maxResults": max_results,
            "relevanceLanguage": "en",
            "key": self.config.YOUTUBE_API_KEY,
        }

        response = requests.get(f"{self.base_url}/search", params=params, timeout=20)
        response.raise_for_status()
        items = response.json().get("items", [])
        return [item.get("id", {}).get("videoId") for item in items if item.get("id", {}).get("videoId")]

    def _fetch_video_details(self, ids: List[str]) -> List[Dict[str, Any]]:
        params = {
            "part": "snippet,statistics",
            "id": ",".join(ids[:50]),
            "key": self.config.YOUTUBE_API_KEY,
        }
        response = requests.get(f"{self.base_url}/videos", params=params, timeout=20)
        response.raise_for_status()
        items = response.json().get("items", [])

        out: List[Dict[str, Any]] = []
        for item in items:
            snippet = item.get("snippet", {})
            stats = item.get("statistics", {})
            published_at = snippet.get("publishedAt")
            published_date = None
            if published_at:
                published_date = datetime.fromisoformat(published_at.replace("Z", "+00:00"))

            title = snippet.get("title", "")
            description = snippet.get("description", "")
            video_id = item.get("id", "")

            out.append(
                {
                    "title": title,
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "source": "YouTube",
                    "published_date": published_date,
                    "description": description,
                    "author": snippet.get("channelTitle", ""),
                    "view_count": int(stats.get("viewCount", 0) or 0),
                    "like_count": int(stats.get("likeCount", 0) or 0),
                    "comments_count": int(stats.get("commentCount", 0) or 0),
                    "keywords": self.filter.extract_keywords_from_text(f"{title} {description}"),
                }
            )

        return out

    def _is_valid_video(self, video: Dict[str, Any]) -> bool:
        if not video:
            return False
        title = video.get("title", "")
        description = video.get("description", "")
        published_date = video.get("published_date")
        view_count = video.get("view_count", 0)

        if not self.filter.contains_ai_keywords(f"{title} {description}"):
            return False
        if not self.filter.is_recent_news(published_date, self.config.NEWS_LOOKBACK_DAYS * 24):
            return False
        if view_count < self.config.YOUTUBE_MIN_VIEWS:
            return False
        return len(title) >= 10
