import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any
import praw
from utils.config import Config
from utils.filters import NewsFilter

class RedditParser:
    """Парсер для Reddit с использованием praw"""
    
    def __init__(self):
        self.config = Config()
        self.filter = NewsFilter()
        self.logger = logging.getLogger(__name__)
        
        # Инициализируем Reddit API
        if not self.config.REDDIT_CLIENT_ID or not self.config.REDDIT_CLIENT_SECRET:
            raise ValueError("Reddit API credentials не установлены")
        
        self.reddit = praw.Reddit(
            client_id=self.config.REDDIT_CLIENT_ID,
            client_secret=self.config.REDDIT_CLIENT_SECRET,
            user_agent=self.config.REDDIT_USER_AGENT
        )
    
    def search_posts(self, max_results: int = 50) -> List[Dict[str, Any]]:
        """Поиск топ-постов по сабреддитам за последние 7 дней"""
        posts = []
        
        try:
            # Поиск по каждому сабреддиту
            for subreddit_name in self.config.REDDIT_SUBREDDITS:
                try:
                    subreddit_posts = self._search_subreddit(subreddit_name, max_results // len(self.config.REDDIT_SUBREDDITS))
                    posts.extend(subreddit_posts)
                    
                    self.logger.info(f"Найдено {len(subreddit_posts)} постов в r/{subreddit_name}")
                    
                except Exception as e:
                    self.logger.error(f"Ошибка при поиске в r/{subreddit_name}: {e}")
                    continue
            
            # Дополнительно: новые инструменты для агентов и автоматизации
            posts.extend(self._search_discovery_posts())

            # Удаляем дубликаты
            posts = self.filter.remove_duplicates(posts)
            posts.sort(key=lambda x: (x.get("score", 0), x.get("comments_count", 0)), reverse=True)
            
            self.logger.info(f"Всего найдено уникальных постов: {len(posts)}")
            return posts
            
        except Exception as e:
            self.logger.error(f"Ошибка при поиске постов: {e}")
            return []
    
    def _search_subreddit(self, subreddit_name: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """Поиск постов в конкретном сабреддите"""
        posts = []
        
        try:
            subreddit = self.reddit.subreddit(subreddit_name)
            
            # Получаем топ-посты за неделю
            top_posts = subreddit.top(time_filter='week', limit=max_results)

            for post in top_posts:
                post_data = self._extract_post_data(post)
                if post_data and self._is_valid_post(post_data):
                    posts.append(post_data)
            
            return posts
            
        except Exception as e:
            self.logger.error(f"Ошибка при поиске в r/{subreddit_name}: {e}")
            return []
    
    def _extract_post_data(self, post) -> Dict[str, Any]:
        """Извлекает данные о посте"""
        try:
            # Парсим дату публикации с UTC часовым поясом
            from datetime import timezone
            published_date = datetime.fromtimestamp(post.created_utc, tz=timezone.utc)
            
            # Проверяем, что пост за последние N дней
            if not self.filter.is_recent_news(published_date, self.config.NEWS_LOOKBACK_DAYS * 24):
                return None
            
            # Всегда используем ссылку на сам пост в Reddit
            reddit_url = f"https://reddit.com{post.permalink}"
            
            # Определяем тип контента для лучшего понимания
            content_type = self._get_content_type(post)
            
            selftext = getattr(post, "selftext", None) or ""
            post_data = {
                'title': post.title,
                'url': reddit_url,
                'description': (selftext.strip() or "")[:4000],
                'author': str(post.author) if post.author else 'deleted',
                'published_date': published_date,
                'score': post.score,
                'source': f'Reddit r/{post.subreddit}',
                'comments_count': post.num_comments,
                'subreddit': post.subreddit,
                'content_type': content_type,
                'keywords': self.filter.extract_keywords_from_text(post.title + ' ' + selftext)
            }
            
            return post_data
            
        except Exception as e:
            self.logger.error(f"Ошибка при извлечении данных поста: {e}")
            return None
    
    def _get_content_type(self, post) -> str:
        """Определяет тип контента поста"""
        try:
            # Проверяем, есть ли текст поста
            if hasattr(post, 'selftext') and post.selftext and post.selftext != '[deleted]':
                return 'text'
            
            # Проверяем URL для определения типа контента
            url = post.url.lower()
            
            # Изображения
            if any(ext in url for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', 'imgur.com', 'i.redd.it']):
                return 'image'
            
            # Видео
            if any(ext in url for ext in ['.mp4', '.webm', '.mov', 'vimeo.com', 'streamable.com']):
                return 'video'
            
            # Внешние ссылки
            if url.startswith('http') and not any(domain in url for domain in ['reddit.com', 'redd.it']):
                return 'link'
            
            # По умолчанию - текст
            return 'text'
            
        except Exception as e:
            self.logger.warning(f"Ошибка при определении типа контента: {e}")
            return 'unknown'
    
    def _is_valid_post(self, post_data: Dict[str, Any]) -> bool:
        """Проверяет, подходит ли пост для включения в AI-дайджест Reddit."""
        if not post_data:
            return False
        
        title = (post_data.get("title") or "").strip()
        if len(title) < 15:
            return False
        lower = title.lower()
        if lower in ("[deleted]", "[removed]"):
            return False
        
        # В AI-режиме Reddit берём топы по сабреддитам за неделю,
        # поэтому фильтр по ключевым словам не применяем.
        # Отсекаем только слабые посты по score.
        score = post_data.get("score", 0)
        if score < 5:
            return False
        
        return True
    
    def get_trending_posts(self, max_results: int = 30) -> List[Dict[str, Any]]:
        """Получает трендовые посты по теме ИИ"""
        posts = []
        
        try:
            # Поиск по всем сабреддитам
            for subreddit_name in self.config.REDDIT_SUBREDDITS:
                try:
                    subreddit = self.reddit.subreddit(subreddit_name)
                    
                    # Получаем топ посты
                    top_posts = subreddit.top(time_filter='week', limit=max_results // len(self.config.REDDIT_SUBREDDITS))
                    
                    for post in top_posts:
                        post_data = self._extract_post_data(post)
                        if post_data and self._is_valid_post(post_data):
                            posts.append(post_data)
                    
                except Exception as e:
                    self.logger.error(f"Ошибка при получении трендовых постов из r/{subreddit_name}: {e}")
                    continue
            
            self.logger.info(f"Найдено {len(posts)} трендовых постов")
            return posts
            
        except Exception as e:
            self.logger.error(f"Ошибка при получении трендовых постов: {e}")
            return []
    
    def _search_discovery_posts(self, limit_per_keyword: int = 8) -> List[Dict[str, Any]]:
        """Ищет по всему Reddit новые инструменты для агентов и автоматизации."""
        posts = []
        keywords = getattr(self.config, "DISCOVERY_KEYWORDS", []) or []

        for keyword in keywords:
            try:
                search_results = self.reddit.subreddit("all").search(
                    keyword, sort="top", time_filter="week", limit=limit_per_keyword
                )
                found = 0
                for post in search_results:
                    post_data = self._extract_post_data(post)
                    if not post_data or not self._is_valid_post(post_data):
                        continue
                    text = f"{post_data.get('title', '')} {post_data.get('description', '')}"
                    if not self.filter.matches_discovery(text):
                        continue
                    posts.append(post_data)
                    found += 1
                self.logger.info("Reddit discovery '%s': %s постов", keyword, found)
            except Exception as e:
                self.logger.error("Ошибка поиска Reddit '%s': %s", keyword, e)
                continue

        return posts

    def search_by_keywords(self, max_results: int = 30) -> List[Dict[str, Any]]:
        """Поиск постов по ключевым словам"""
        posts = []
        
        try:
            # Поиск по каждому ключевому слову
            for keyword in self.config.AI_KEYWORDS:  # Ограничиваем количество запросов
                try:
                    # Поиск по всем сабреддитам
                    for subreddit_name in self.config.REDDIT_SUBREDDITS:
                        try:
                            subreddit = self.reddit.subreddit(subreddit_name)
                            
                            # Поиск по ключевому слову
                            search_results = subreddit.search(keyword, sort='top', time_filter='week', limit=5)
                            
                            for post in search_results:
                                post_data = self._extract_post_data(post)
                                if post_data and self._is_valid_post(post_data):
                                    posts.append(post_data)
                            
                        except Exception as e:
                            self.logger.error(f"Ошибка при поиске '{keyword}' в r/{subreddit_name}: {e}")
                            continue
                    
                except Exception as e:
                    self.logger.error(f"Ошибка при поиске по ключевому слову '{keyword}': {e}")
                    continue
            
            # Удаляем дубликаты
            posts = self.filter.remove_duplicates(posts)
            
            self.logger.info(f"Найдено {len(posts)} постов по ключевым словам")
            return posts
            
        except Exception as e:
            self.logger.error(f"Ошибка при поиске постов по ключевым словам: {e}")
            return []

    def _is_valid_business_post(self, post_data: Dict[str, Any]) -> bool:
        """Пост про бизнес-идеи / истории запуска; без фильтра по ИИ."""
        if not post_data:
            return False
        title = (post_data.get("title") or "").strip()
        if len(title) < 15:
            return False
        lower = title.lower()
        if lower in ("[deleted]", "[removed]"):
            return False
        score = post_data.get("score", 0)
        if score < self.config.REDDIT_BUSINESS_MIN_SCORE:
            return False
        return self.filter.is_business_idea_post(post_data)

    def search_business_posts(self, max_results: int = 50) -> List[Dict[str, Any]]:
        """
        Популярные посты про бизнес-идеи и истории запуска:
        top(week) по сабам + фильтр по ключевым словам / idea-сабам.
        """
        posts: List[Dict[str, Any]] = []
        subs = self.config.REDDIT_BUSINESS_SUBREDDITS
        limit_per_sub = max(3, self.config.REDDIT_BUSINESS_TOP_PER_SUB)

        try:
            for subreddit_name in subs:
                try:
                    subreddit = self.reddit.subreddit(subreddit_name)
                    for post in subreddit.top(time_filter="week", limit=limit_per_sub):
                        if getattr(post, "stickied", False):
                            continue
                        post_data = self._extract_post_data(post)
                        if post_data and self._is_valid_business_post(post_data):
                            posts.append(post_data)
                    self.logger.debug(
                        "Бизнес-идеи Reddit: r/%s (top за неделю, limit=%s)",
                        subreddit_name,
                        limit_per_sub,
                    )
                except Exception as e:
                    self.logger.error("Ошибка бизнес-сбора в r/%s: %s", subreddit_name, e)
                    continue

            posts = self.filter.remove_duplicates(posts)
            posts.sort(
                key=lambda x: (
                    self.filter.business_idea_relevance(x),
                    x.get("score", 0),
                ),
                reverse=True,
            )
            if len(posts) > max_results:
                posts = posts[:max_results]
            self.logger.info(
                "Бизнес-идеи Reddit: уникальных постов после среза: %s", len(posts)
            )
            return posts
        except Exception as e:
            self.logger.error("Ошибка search_business_posts: %s", e)
            return []
