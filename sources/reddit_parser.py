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
        """Поиск постов по сабреддитам за последние 24 часа"""
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
            
            # Удаляем дубликаты
            posts = self.filter.remove_duplicates(posts)
            
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
            
            # Получаем горячие посты
            hot_posts = subreddit.hot(limit=max_results)
            
            for post in hot_posts:
                post_data = self._extract_post_data(post)
                if post_data and self._is_valid_post(post_data):
                    posts.append(post_data)
            
            # Получаем новые посты
            new_posts = subreddit.new(limit=max_results)
            
            for post in new_posts:
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
            
            # Проверяем, что пост свежий (за последние 24 часа)
            if not self.filter.is_recent_news(published_date, 24):
                return None
            
            # Всегда используем ссылку на сам пост в Reddit
            reddit_url = f"https://reddit.com{post.permalink}"
            
            # Определяем тип контента для лучшего понимания
            content_type = self._get_content_type(post)
            
            post_data = {
                'title': post.title,
                'url': reddit_url,
                'author': str(post.author) if post.author else 'deleted',
                'published_date': published_date,
                'score': post.score,
                'source': f'Reddit r/{post.subreddit}',
                'comments_count': post.num_comments,
                'subreddit': post.subreddit,
                'content_type': content_type,
                'keywords': self.filter.extract_keywords_from_text(post.title + ' ' + (post.selftext if hasattr(post, 'selftext') else ''))
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
            if any(ext in url for ext in ['.mp4', '.webm', '.mov', 'youtube.com', 'youtu.be', 'vimeo.com', 'streamable.com']):
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
        """Проверяет, подходит ли пост для включения в дайджест"""
        if not post_data:
            return False
        
        title = post_data.get('title', '')
        
        # Проверяем наличие ключевых слов
        if not self.filter.contains_ai_keywords(title):
            return False
        
        # Проверяем минимальную длину заголовка
        if len(title) < 10:
            return False
        
        # Проверяем минимальный рейтинг
        score = post_data.get('score', 0)
        if score < 1:
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
                    top_posts = subreddit.top(time_filter='day', limit=max_results // len(self.config.REDDIT_SUBREDDITS))
                    
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
    
    def search_by_keywords(self, max_results: int = 30) -> List[Dict[str, Any]]:
        """Поиск постов по ключевым словам"""
        posts = []
        
        try:
            # Поиск по каждому ключевому слову
            for keyword in self.config.AI_KEYWORDS[:5]:  # Ограничиваем количество запросов
                try:
                    # Поиск по всем сабреддитам
                    for subreddit_name in self.config.REDDIT_SUBREDDITS:
                        try:
                            subreddit = self.reddit.subreddit(subreddit_name)
                            
                            # Поиск по ключевому слову
                            search_results = subreddit.search(keyword, sort='new', time_filter='day', limit=5)
                            
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
