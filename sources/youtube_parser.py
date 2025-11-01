import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from utils.config import Config
from utils.filters import NewsFilter

class YouTubeParser:
    """Парсер для YouTube с использованием YouTube Data API v3"""
    
    def __init__(self):
        self.config = Config()
        self.filter = NewsFilter()
        self.logger = logging.getLogger(__name__)
        
        if not self.config.YOUTUBE_API_KEY:
            raise ValueError("YouTube API ключ не установлен")
        
        # Инициализируем YouTube API
        self.youtube = build('youtube', 'v3', developerKey=self.config.YOUTUBE_API_KEY)
    
    def search_videos(self, max_results: int = 50) -> List[Dict[str, Any]]:
        """Поиск видео по ключевым словам за последние 24 часа"""
        videos = []
        
        try:
            # Вычисляем время 24 часа назад в формате ISO 8601 для YouTube API
            from datetime import timezone
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=24)
            # Убираем микросекунды для YouTube API
            cutoff_time = cutoff_time.replace(microsecond=0)
            published_after = cutoff_time.strftime('%Y-%m-%dT%H:%M:%S.000Z')
            
            # Поиск по каждому ключевому слову
            for keyword in self.config.AI_KEYWORDS[:15]:  # Увеличиваем количество запросов
                try:
                    search_response = self.youtube.search().list(
                        part='snippet',
                        q=keyword,
                        type='video',
                        order='date',
                        publishedAfter=published_after,
                        maxResults=min(max_results, 50),  # YouTube API лимит
                        regionCode='US',
                        relevanceLanguage='en',
                        safeSearch='moderate'
                    ).execute()
                    
                    for item in search_response.get('items', []):
                        video_data = self._extract_video_data(item)
                        if video_data and self._is_valid_video(video_data):
                            # Получаем информацию о канале
                            channel_id = item['snippet'].get('channelId', '')
                            channel_info = self._get_channel_info(channel_id)
                            
                            # Проверяем язык канала и страну
                            if not self._is_english_or_russian_channel(channel_info, video_data.get('title', '')):
                                continue
                            
                            # Получаем длительность видео
                            duration = self._get_video_duration(video_data.get('url', ''))
                            if duration and duration >= 180:  # 3 минуты = 180 секунд
                                video_data['duration'] = duration
                                video_data['channel_info'] = channel_info
                                videos.append(video_data)
                    
                    self.logger.info(f"Найдено {len(search_response.get('items', []))} видео для ключевого слова: {keyword}")
                    
                except HttpError as e:
                    self.logger.error(f"Ошибка при поиске видео для '{keyword}': {e}")
                    continue
            
            # Удаляем дубликаты
            videos = self.filter.remove_duplicates(videos)
            
            self.logger.info(f"Всего найдено уникальных видео: {len(videos)}")
            return videos
            
        except Exception as e:
            self.logger.error(f"Ошибка при поиске видео на YouTube: {e}")
            return []
    
    def _extract_video_data(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Извлекает данные о видео из ответа API"""
        try:
            snippet = item.get('snippet', {})
            
            # Получаем ID видео безопасно
            video_id = ''
            if 'id' in item:
                if isinstance(item['id'], dict):
                    video_id = item['id'].get('videoId', '')
                else:
                    video_id = str(item['id'])
            
            # Парсим дату публикации
            published_at = snippet.get('publishedAt', '')
            published_date = None
            
            if published_at:
                try:
                    # Обрабатываем разные форматы даты
                    if published_at.endswith('Z'):
                        published_date = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
                    else:
                        published_date = datetime.fromisoformat(published_at)
                    
                    # Убеждаемся, что дата имеет часовой пояс UTC
                    from datetime import timezone
                    if published_date.tzinfo is None:
                        published_date = published_date.replace(tzinfo=timezone.utc)
                    
                except ValueError as date_error:
                    self.logger.warning(f"Ошибка парсинга даты '{published_at}': {date_error}")
                    published_date = None
            
            # Проверяем, что видео свежее 24 часов
            if not self.filter.is_recent_news(published_date, 24):
                return None
            
            # Безопасно извлекаем ключевые слова
            title = snippet.get('title', '')
            description = snippet.get('description', '')
            combined_text = f"{title} {description}"
            
            try:
                keywords = self.filter.extract_keywords_from_text(combined_text)
            except Exception as keyword_error:
                self.logger.warning(f"Ошибка извлечения ключевых слов: {keyword_error}")
                keywords = []
            
            video_data = {
                'title': title,
                'url': f"https://www.youtube.com/watch?v={video_id}" if video_id else '',
                'channel': snippet.get('channelTitle', ''),
                'description': description,
                'published_date': published_date,
                'source': 'YouTube',
                'keywords': keywords
            }
            
            return video_data
            
        except Exception as e:
            self.logger.error(f"Ошибка при извлечении данных видео: {e}")
            self.logger.debug(f"Проблемный item: {item}")
            return None
    
    def _get_video_duration(self, video_url: str) -> int:
        """Получает длительность видео в секундах"""
        try:
            # Извлекаем video_id из URL
            if 'watch?v=' in video_url:
                video_id = video_url.split('watch?v=')[1].split('&')[0]
            else:
                return None
            
            # Получаем детальную информацию о видео
            video_response = self.youtube.videos().list(
                part='contentDetails',
                id=video_id
            ).execute()
            
            if video_response.get('items'):
                duration_str = video_response['items'][0]['contentDetails']['duration']
                return self._parse_duration(duration_str)
            
            return None
            
        except Exception as e:
            self.logger.warning(f"Ошибка получения длительности видео {video_url}: {e}")
            return None
    
    def _get_channel_info(self, channel_id: str) -> dict:
        """Получает информацию о канале"""
        try:
            channel_response = self.youtube.channels().list(
                part='snippet,statistics',
                id=channel_id
            ).execute()
            
            if channel_response.get('items'):
                channel = channel_response['items'][0]
                return {
                    'title': channel['snippet'].get('title', ''),
                    'description': channel['snippet'].get('description', ''),
                    'country': channel['snippet'].get('country', ''),
                    'default_language': channel['snippet'].get('defaultLanguage', ''),
                    'view_count': channel['statistics'].get('viewCount', '0')
                }
            
            return {}
            
        except Exception as e:
            self.logger.warning(f"Ошибка получения информации о канале {channel_id}: {e}")
            return {}
    
    def _is_english_or_russian_channel(self, channel_info: dict, video_title: str) -> bool:
        """Проверяет, является ли канал англоязычным или русскоязычным"""
        if not channel_info:
            # Если нет информации о канале, проверяем только название видео
            return self.filter.is_english_or_russian(video_title)
        
        # Проверяем страну канала
        country = channel_info.get('country', '').upper()
        if country in ['US', 'GB', 'CA', 'AU', 'NZ', 'IE', 'RU', 'BY', 'KZ', 'KG', 'TJ', 'UZ', 'AM', 'AZ', 'GE', 'MD', 'UA']:
            return True
        
        # Проверяем язык канала
        default_language = channel_info.get('default_language', '').lower()
        if default_language in ['en', 'ru']:
            return True
        
        # Проверяем название и описание канала
        channel_title = channel_info.get('title', '')
        channel_description = channel_info.get('description', '')
        
        if self.filter.is_english_or_russian(channel_title) or self.filter.is_english_or_russian(channel_description):
            return True
        
        # Проверяем название видео
        return self.filter.is_english_or_russian(video_title)
    
    def _parse_duration(self, duration_str: str) -> int:
        """Парсит длительность в формате ISO 8601 (PT1H2M3S) в секунды"""
        try:
            import re
            # Убираем PT и парсим компоненты
            duration_str = duration_str.replace('PT', '')
            
            # Ищем часы, минуты и секунды
            hours = re.search(r'(\d+)H', duration_str)
            minutes = re.search(r'(\d+)M', duration_str)
            seconds = re.search(r'(\d+)S', duration_str)
            
            total_seconds = 0
            if hours:
                total_seconds += int(hours.group(1)) * 3600
            if minutes:
                total_seconds += int(minutes.group(1)) * 60
            if seconds:
                total_seconds += int(seconds.group(1))
            
            return total_seconds
            
        except Exception as e:
            self.logger.warning(f"Ошибка парсинга длительности '{duration_str}': {e}")
            return 0

    def _is_valid_video(self, video_data: Dict[str, Any]) -> bool:
        """Проверяет, подходит ли видео для включения в дайджест"""
        if not video_data:
            return False
        
        title = video_data.get('title', '')
        description = video_data.get('description', '')
        
        # Проверяем наличие ключевых слов
        if not self.filter.contains_ai_keywords(title + ' ' + description):
            return False
        
        # Проверяем, что это не научная статья
        text = (title + ' ' + description).lower()
        exclude_keywords = self.config.EXCLUDE_KEYWORDS
        
        for exclude_word in exclude_keywords:
            if exclude_word.lower() in text:
                return False
        
        return True
    
    def get_trending_videos(self, max_results: int = 20) -> List[Dict[str, Any]]:
        """Получает трендовые видео по категории Science & Technology"""
        videos = []
        
        try:
            # Получаем трендовые видео
            trending_response = self.youtube.videos().list(
                part='snippet,statistics',
                chart='mostPopular',
                regionCode='US',
                maxResults=max_results,
                categoryId='28'  # Science & Technology
            ).execute()
            
            for item in trending_response.get('items', []):
                video_data = self._extract_trending_video_data(item)
                if video_data and self._is_valid_video(video_data):
                    videos.append(video_data)
            
            self.logger.info(f"Найдено {len(videos)} трендовых видео")
            return videos
            
        except Exception as e:
            self.logger.error(f"Ошибка при получении трендовых видео: {e}")
            return []
    
    def _extract_trending_video_data(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Извлекает данные о трендовом видео"""
        try:
            snippet = item.get('snippet', {})
            statistics = item.get('statistics', {})
            
            # Получаем ID видео безопасно
            video_id = item.get('id', '')
            
            # Парсим дату публикации
            published_at = snippet.get('publishedAt', '')
            published_date = None
            
            if published_at:
                try:
                    # Обрабатываем разные форматы даты
                    if published_at.endswith('Z'):
                        published_date = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
                    else:
                        published_date = datetime.fromisoformat(published_at)
                    
                    # Убеждаемся, что дата имеет часовой пояс UTC
                    from datetime import timezone
                    if published_date.tzinfo is None:
                        published_date = published_date.replace(tzinfo=timezone.utc)
                    
                except ValueError as date_error:
                    self.logger.warning(f"Ошибка парсинга даты трендового видео '{published_at}': {date_error}")
                    published_date = None
            
            # Безопасно извлекаем ключевые слова
            title = snippet.get('title', '')
            description = snippet.get('description', '')
            combined_text = f"{title} {description}"
            
            try:
                keywords = self.filter.extract_keywords_from_text(combined_text)
            except Exception as keyword_error:
                self.logger.warning(f"Ошибка извлечения ключевых слов трендового видео: {keyword_error}")
                keywords = []
            
            video_data = {
                'title': title,
                'url': f"https://www.youtube.com/watch?v={video_id}" if video_id else '',
                'channel': snippet.get('channelTitle', ''),
                'description': description,
                'published_date': published_date,
                'source': 'YouTube (Trending)',
                'view_count': statistics.get('viewCount', 0),
                'keywords': keywords
            }
            
            return video_data
            
        except Exception as e:
            self.logger.error(f"Ошибка при извлечении данных трендового видео: {e}")
            self.logger.debug(f"Проблемный item: {item}")
            return None
