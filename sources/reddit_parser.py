import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Sequence
import praw
from utils.config import Config
from utils.filters import NewsFilter


class RedditParser:
    """Парсер Reddit: AI-сабы + онлайн-бизнес с ИИ."""

    def __init__(self, active_keywords: Optional[Sequence[str]] = None):
        self.config = Config()
        self.filter = NewsFilter(active_keywords)
        self.logger = logging.getLogger(__name__)

        if not self.config.REDDIT_CLIENT_ID or not self.config.REDDIT_CLIENT_SECRET:
            raise ValueError("Reddit API credentials не установлены")

        self.reddit = praw.Reddit(
            client_id=self.config.REDDIT_CLIENT_ID,
            client_secret=self.config.REDDIT_CLIENT_SECRET,
            user_agent=self.config.REDDIT_USER_AGENT,
        )

    def set_active_keywords(self, keywords: Sequence[str]) -> None:
        self.filter.set_active_keywords(keywords)

    def search_posts(self, max_results: int = 50) -> List[Dict[str, Any]]:
        """Топ AI-сабов за неделю + поиск по active-ключевым словам."""
        posts: List[Dict[str, Any]] = []
        subs = self.config.REDDIT_SUBREDDITS
        per_sub = max(3, max_results // max(len(subs), 1))

        for subreddit_name in subs:
            try:
                posts.extend(self._search_subreddit(subreddit_name, per_sub))
            except Exception as e:
                self.logger.error("Ошибка r/%s: %s", subreddit_name, e)

        posts.extend(self._search_by_active_keywords(limit_per_kw=5))
        posts = self.filter.remove_duplicates(posts)
        posts.sort(key=lambda x: (x.get("score", 0), x.get("comments_count", 0)), reverse=True)
        return posts[:max_results]

    def search_business_posts(self, max_results: int = 50) -> List[Dict[str, Any]]:
        """Онлайн-бизнес сабы: только посты про ИИ и онлайн."""
        posts: List[Dict[str, Any]] = []
        subs = self.config.REDDIT_BUSINESS_SUBREDDITS
        limit_per_sub = max(3, self.config.REDDIT_BUSINESS_TOP_PER_SUB)

        for subreddit_name in subs:
            try:
                subreddit = self.reddit.subreddit(subreddit_name)
                for post in subreddit.top(time_filter="week", limit=limit_per_sub):
                    if getattr(post, "stickied", False):
                        continue
                    post_data = self._extract_post_data(post)
                    if post_data and self._is_valid_business_post(post_data):
                        posts.append(post_data)
            except Exception as e:
                self.logger.error("Ошибка бизнес-сбора r/%s: %s", subreddit_name, e)

        posts = self.filter.remove_duplicates(posts)
        posts.sort(key=lambda x: x.get("score", 0), reverse=True)
        return posts[:max_results]

    def _search_subreddit(self, subreddit_name: str, max_results: int = 10) -> List[Dict[str, Any]]:
        posts = []
        subreddit = self.reddit.subreddit(subreddit_name)
        for post in subreddit.top(time_filter="week", limit=max_results):
            post_data = self._extract_post_data(post)
            if post_data and self._is_valid_ai_post(post_data):
                posts.append(post_data)
        return posts

    def _search_by_active_keywords(self, limit_per_kw: int = 5) -> List[Dict[str, Any]]:
        posts = []
        keywords = self.filter.active_keywords[:15]
        for keyword in keywords:
            try:
                for post in self.reddit.subreddit("all").search(
                    keyword, sort="top", time_filter="week", limit=limit_per_kw
                ):
                    post_data = self._extract_post_data(post)
                    if post_data and self._is_valid_ai_post(post_data):
                        posts.append(post_data)
            except Exception as e:
                self.logger.error("Ошибка поиска Reddit '%s': %s", keyword, e)
        return posts

    def _extract_post_data(self, post) -> Dict[str, Any]:
        try:
            from datetime import timezone

            published_date = datetime.fromtimestamp(post.created_utc, tz=timezone.utc)
            if not self.filter.is_recent_news(published_date, self.config.NEWS_LOOKBACK_DAYS * 24):
                return None

            reddit_url = f"https://reddit.com{post.permalink}"
            selftext = getattr(post, "selftext", None) or ""
            return {
                "title": post.title,
                "url": reddit_url,
                "description": (selftext.strip() or "")[:4000],
                "author": str(post.author) if post.author else "deleted",
                "published_date": published_date,
                "score": post.score,
                "source": f"Reddit r/{post.subreddit}",
                "comments_count": post.num_comments,
                "subreddit": str(post.subreddit),
                "content_type": self._get_content_type(post),
                "keywords": self.filter.extract_keywords_from_text(post.title + " " + selftext),
            }
        except Exception as e:
            self.logger.error("Ошибка извлечения поста: %s", e)
            return None

    def _get_content_type(self, post) -> str:
        try:
            if hasattr(post, "selftext") and post.selftext and post.selftext != "[deleted]":
                return "text"
            url = post.url.lower()
            if any(ext in url for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp", "imgur.com", "i.redd.it"]):
                return "image"
            if any(ext in url for ext in [".mp4", ".webm", ".mov", "vimeo.com", "streamable.com"]):
                return "video"
            if url.startswith("http") and not any(d in url for d in ["reddit.com", "redd.it"]):
                return "link"
            return "text"
        except Exception:
            return "unknown"

    def _is_valid_ai_post(self, post_data: Dict[str, Any]) -> bool:
        if not post_data:
            return False
        title = (post_data.get("title") or "").strip()
        if len(title) < 15:
            return False
        if title.lower() in ("[deleted]", "[removed]"):
            return False
        if post_data.get("score", 0) < 5:
            return False
        return True

    def _is_valid_business_post(self, post_data: Dict[str, Any]) -> bool:
        if not post_data:
            return False
        title = (post_data.get("title") or "").strip()
        if len(title) < 15:
            return False
        if title.lower() in ("[deleted]", "[removed]"):
            return False
        if post_data.get("score", 0) < self.config.REDDIT_BUSINESS_MIN_SCORE:
            return False
        return self.filter.is_online_ai_business_post(post_data)
