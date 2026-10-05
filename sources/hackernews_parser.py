import logging
import time
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional, Sequence
import requests
from utils.config import Config
from utils.filters import NewsFilter


class HackerNewsParser:
    """Парсер Hacker News: топ + поиск по active-ключевым словам."""

    def __init__(self, active_keywords: Optional[Sequence[str]] = None):
        self.config = Config()
        self.filter = NewsFilter(active_keywords)
        self.logger = logging.getLogger(__name__)
        self.base_url = "https://hacker-news.firebaseio.com/v0"

    def set_active_keywords(self, keywords: Sequence[str]) -> None:
        self.filter.set_active_keywords(keywords)

    def search_stories(self, max_results: int = 50) -> List[Dict[str, Any]]:
        stories: List[Dict[str, Any]] = []
        session = requests.Session()
        try:
            stories.extend(self._fetch_firebase_stories(session, max_results))
            stories.extend(self._search_by_active_keywords(session))
            stories = self.filter.remove_duplicates(stories)
            stories.sort(key=lambda x: (x.get("score", 0), x.get("comments_count", 0)), reverse=True)
            return stories[:max_results]
        except Exception as e:
            self.logger.error("Ошибка поиска HN: %s", e)
            return []
        finally:
            session.close()

    def _fetch_firebase_stories(self, session: requests.Session, max_results: int) -> List[Dict[str, Any]]:
        """Топ/best через Firebase; при недоступности хоста — одна запись в лог, без запросов историй."""
        try:
            top_resp = session.get(f"{self.base_url}/topstories.json", timeout=30)
            top_resp.raise_for_status()
            best_resp = session.get(f"{self.base_url}/beststories.json", timeout=30)
            best_resp.raise_for_status()
            top_ids = top_resp.json() or []
            best_ids = best_resp.json() or []
        except (requests.ConnectionError, requests.Timeout, OSError) as e:
            self.logger.error("HN Firebase недоступен, шаг пропущен: %s", e)
            return []
        except Exception as e:
            self.logger.error("HN Firebase: ошибка списков историй: %s", e)
            return []

        stories: List[Dict[str, Any]] = []
        all_ids = (best_ids + top_ids)[: max_results * 3]
        for story_id in all_ids:
            try:
                story_data = self._get_story_details(session, story_id)
                if story_data and self._is_valid_story(story_data):
                    stories.append(story_data)
                    if len(stories) >= max_results:
                        break
            except (requests.ConnectionError, requests.Timeout, OSError) as e:
                self.logger.error("HN Firebase: соединение прервано, загрузка историй остановлена: %s", e)
                break
            except Exception:
                # 404 / пустая история / прочий HTTP — пропустить эту историю
                continue
        return stories

    def _get_story_details(self, session: requests.Session, story_id: int) -> Optional[Dict[str, Any]]:
        response = session.get(f"{self.base_url}/item/{story_id}.json", timeout=20)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        story = response.json()
        if not story or story.get("type") != "story":
            return None

        published_timestamp = story.get("time")
        published_date = (
            datetime.fromtimestamp(published_timestamp, tz=timezone.utc)
            if published_timestamp
            else None
        )
        if not self.filter.is_recent_news(published_date, self.config.NEWS_LOOKBACK_DAYS * 24):
            return None

        return {
            "title": story.get("title", ""),
            "url": story.get("url", f"https://news.ycombinator.com/item?id={story_id}"),
            "author": story.get("by", ""),
            "published_date": published_date,
            "score": story.get("score", 0),
            "source": "Hacker News",
            "comments_count": story.get("descendants", 0),
            "keywords": self.filter.extract_keywords_from_text(story.get("title", "")),
        }

    def _is_valid_story(self, story_data: Dict[str, Any]) -> bool:
        if not story_data:
            return False
        title = story_data.get("title", "")
        if not self.filter.contains_ai_keywords(title):
            return False
        if len(title) < 10:
            return False
        if story_data.get("score", 0) < 1:
            return False
        return True

    def _search_by_active_keywords(
        self, session: requests.Session, hits_per_query: int = 8
    ) -> List[Dict[str, Any]]:
        stories = []
        keywords = self.filter.active_keywords[:20]
        since = datetime.now(timezone.utc) - timedelta(days=self.config.NEWS_LOOKBACK_DAYS)
        since_ts = int(since.timestamp())

        for index, keyword in enumerate(keywords):
            if index > 0:
                time.sleep(0.3)
            try:
                response = session.get(
                    "https://hn.algolia.com/api/v1/search_by_date",
                    params={
                        "query": keyword,
                        "tags": "story",
                        "numericFilters": f"created_at_i>{since_ts}",
                        "hitsPerPage": hits_per_query,
                    },
                    timeout=20,
                )
                response.raise_for_status()
                for hit in response.json().get("hits", []):
                    story = self._story_from_algolia(hit)
                    if story and self._is_valid_story(story):
                        stories.append(story)
            except (requests.ConnectionError, requests.Timeout, OSError) as e:
                self.logger.error("HN Algolia недоступен, поиск по словам остановлен: %s", e)
                break
            except Exception as e:
                self.logger.error("Ошибка поиска HN '%s': %s", keyword, e)
        return stories

    def _story_from_algolia(self, hit: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        title = (hit or {}).get("title") or ""
        if not title:
            return None
        created = hit.get("created_at_i")
        published_date = datetime.fromtimestamp(created, tz=timezone.utc) if created else None
        if not self.filter.is_recent_news(published_date, self.config.NEWS_LOOKBACK_DAYS * 24):
            return None
        story_id = hit.get("objectID")
        url = hit.get("url") or (f"https://news.ycombinator.com/item?id={story_id}" if story_id else "")
        return {
            "title": title,
            "url": url,
            "author": hit.get("author", ""),
            "published_date": published_date,
            "score": hit.get("points", 0) or 0,
            "source": "Hacker News",
            "comments_count": hit.get("num_comments", 0) or 0,
            "keywords": self.filter.extract_keywords_from_text(title),
        }
