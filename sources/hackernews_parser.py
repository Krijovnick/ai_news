import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any
import requests
from utils.config import Config
from utils.filters import NewsFilter

class HackerNewsParser:
    """Парсер для Hacker News с использованием официального API"""
    
    def __init__(self):
        self.config = Config()
        self.filter = NewsFilter()
        self.logger = logging.getLogger(__name__)
        self.base_url = "https://hacker-news.firebaseio.com/v0"
    
    def search_stories(self, max_results: int = 50) -> List[Dict[str, Any]]:
        """Поиск историй по ключевым словам за последние 24 часа"""
        stories = []
        
        try:
            # Получаем ID топ историй
            top_stories_response = requests.get(f"{self.base_url}/topstories.json")
            top_stories_response.raise_for_status()
            top_story_ids = top_stories_response.json()
            
            # Получаем ID новых историй
            new_stories_response = requests.get(f"{self.base_url}/newstories.json")
            new_stories_response.raise_for_status()
            new_story_ids = new_stories_response.json()
            
            # Объединяем и ограничиваем количество
            all_story_ids = (top_story_ids + new_story_ids)[:max_results * 2]
            
            self.logger.info(f"Проверяем {len(all_story_ids)} историй")
            
            # Получаем детали каждой истории
            for story_id in all_story_ids:
                try:
                    story_data = self._get_story_details(story_id)
                    if story_data and self._is_valid_story(story_data):
                        stories.append(story_data)
                        
                        if len(stories) >= max_results:
                            break
                    
                except Exception as e:
                    self.logger.error(f"Ошибка при получении истории {story_id}: {e}")
                    continue
            
            self.logger.info(f"Найдено {len(stories)} подходящих историй")
            return stories
            
        except Exception as e:
            self.logger.error(f"Ошибка при поиске историй: {e}")
            return []
    
    def _get_story_details(self, story_id: int) -> Dict[str, Any]:
        """Получает детали истории по ID"""
        try:
            response = requests.get(f"{self.base_url}/item/{story_id}.json")
            response.raise_for_status()
            story = response.json()
            
            if not story or story.get('type') != 'story':
                return None
            
            # Парсим дату публикации с UTC часовым поясом
            from datetime import timezone
            published_timestamp = story.get('time')
            if published_timestamp:
                published_date = datetime.fromtimestamp(published_timestamp, tz=timezone.utc)
            else:
                published_date = None
            
            # Проверяем, что история свежая (за последние 24 часа)
            if not self.filter.is_recent_news(published_date, 24):
                return None
            
            story_data = {
                'title': story.get('title', ''),
                'url': story.get('url', f"https://news.ycombinator.com/item?id={story_id}"),
                'author': story.get('by', ''),
                'published_date': published_date,
                'score': story.get('score', 0),
                'source': 'Hacker News',
                'comments_count': story.get('descendants', 0),
                'keywords': self.filter.extract_keywords_from_text(story.get('title', ''))
            }
            
            return story_data
            
        except Exception as e:
            self.logger.error(f"Ошибка при получении деталей истории {story_id}: {e}")
            return None
    
    def _is_valid_story(self, story_data: Dict[str, Any]) -> bool:
        """Проверяет, подходит ли история для включения в дайджест"""
        if not story_data:
            return False
        
        title = story_data.get('title', '')
        
        # Проверяем наличие ключевых слов
        if not self.filter.contains_ai_keywords(title):
            return False
        
        # Проверяем минимальную длину заголовка
        if len(title) < 10:
            return False
        
        # Проверяем минимальный рейтинг
        score = story_data.get('score', 0)
        if score < 1:
            return False
        
        return True
    
    def get_best_stories(self, max_results: int = 30) -> List[Dict[str, Any]]:
        """Получает лучшие истории за последние 24 часа"""
        stories = []
        
        try:
            # Получаем ID лучших историй
            best_stories_response = requests.get(f"{self.base_url}/beststories.json")
            best_stories_response.raise_for_status()
            best_story_ids = best_stories_response.json()
            
            self.logger.info(f"Проверяем {len(best_story_ids)} лучших историй")
            
            # Получаем детали каждой истории
            for story_id in best_story_ids:
                try:
                    story_data = self._get_story_details(story_id)
                    if story_data and self._is_valid_story(story_data):
                        stories.append(story_data)
                        
                        if len(stories) >= max_results:
                            break
                    
                except Exception as e:
                    self.logger.error(f"Ошибка при получении лучшей истории {story_id}: {e}")
                    continue
            
            self.logger.info(f"Найдено {len(stories)} лучших историй")
            return stories
            
        except Exception as e:
            self.logger.error(f"Ошибка при получении лучших историй: {e}")
            return []
    
    def get_ask_hn_stories(self, max_results: int = 20) -> List[Dict[str, Any]]:
        """Получает истории из Ask HN за последние 24 часа"""
        stories = []
        
        try:
            # Получаем ID историй Ask HN
            ask_hn_response = requests.get(f"{self.base_url}/askstories.json")
            ask_hn_response.raise_for_status()
            ask_hn_ids = ask_hn_response.json()
            
            self.logger.info(f"Проверяем {len(ask_hn_ids)} историй Ask HN")
            
            # Получаем детали каждой истории
            for story_id in ask_hn_ids:
                try:
                    story_data = self._get_story_details(story_id)
                    if story_data and self._is_valid_story(story_data):
                        stories.append(story_data)
                        
                        if len(stories) >= max_results:
                            break
                    
                except Exception as e:
                    self.logger.error(f"Ошибка при получении Ask HN истории {story_id}: {e}")
                    continue
            
            self.logger.info(f"Найдено {len(stories)} историй Ask HN")
            return stories
            
        except Exception as e:
            self.logger.error(f"Ошибка при получении историй Ask HN: {e}")
            return []
    
    def get_show_hn_stories(self, max_results: int = 20) -> List[Dict[str, Any]]:
        """Получает истории из Show HN за последние 24 часа"""
        stories = []
        
        try:
            # Получаем ID историй Show HN
            show_hn_response = requests.get(f"{self.base_url}/showstories.json")
            show_hn_response.raise_for_status()
            show_hn_ids = show_hn_response.json()
            
            self.logger.info(f"Проверяем {len(show_hn_ids)} историй Show HN")
            
            # Получаем детали каждой истории
            for story_id in show_hn_ids:
                try:
                    story_data = self._get_story_details(story_id)
                    if story_data and self._is_valid_story(story_data):
                        stories.append(story_data)
                        
                        if len(stories) >= max_results:
                            break
                    
                except Exception as e:
                    self.logger.error(f"Ошибка при получении Show HN истории {story_id}: {e}")
                    continue
            
            self.logger.info(f"Найдено {len(stories)} историй Show HN")
            return stories
            
        except Exception as e:
            self.logger.error(f"Ошибка при получении историй Show HN: {e}")
            return []
