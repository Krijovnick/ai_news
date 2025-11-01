import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any
import snscrape.modules.twitter as sntwitter
from utils.config import Config
from utils.filters import NewsFilter

class TwitterParser:
    """Парсер для Twitter/X с использованием snscrape"""
    
    def __init__(self):
        self.config = Config()
        self.filter = NewsFilter()
        self.logger = logging.getLogger(__name__)
    
    def search_tweets(self, max_results: int = 100) -> List[Dict[str, Any]]:
        """Поиск твитов по хэштегам за последние 24 часа"""
        tweets = []
        
        try:
            # Вычисляем дату 24 часа назад в UTC
            from datetime import timezone
            since_date = datetime.now(timezone.utc) - timedelta(hours=24)
            since_str = since_date.strftime('%Y-%m-%d')
            
            # Поиск по каждому хэштегу
            for hashtag in self.config.TWITTER_HASHTAGS:
                try:
                    # Формируем поисковый запрос
                    query = f"{hashtag} since:{since_str} -filter:retweets"
                    
                    self.logger.info(f"Поиск твитов с запросом: {query}")
                    
                    # Используем snscrape для поиска
                    scraper = sntwitter.TwitterSearchScraper(query)
                    
                    count = 0
                    for tweet in scraper.get_items():
                        if count >= max_results:
                            break
                        
                        tweet_data = self._extract_tweet_data(tweet)
                        if tweet_data and self._is_valid_tweet(tweet_data):
                            tweets.append(tweet_data)
                            count += 1
                    
                    self.logger.info(f"Найдено {count} твитов для хэштега: {hashtag}")
                    
                except Exception as e:
                    self.logger.error(f"Ошибка при поиске твитов для '{hashtag}': {e}")
                    continue
            
            # Удаляем дубликаты
            tweets = self.filter.remove_duplicates(tweets)
            
            self.logger.info(f"Всего найдено уникальных твитов: {len(tweets)}")
            return tweets
            
        except Exception as e:
            self.logger.error(f"Ошибка при поиске твитов: {e}")
            return []
    
    def search_by_keywords(self, max_results: int = 50) -> List[Dict[str, Any]]:
        """Поиск твитов по ключевым словам"""
        tweets = []
        
        try:
            # Вычисляем дату 24 часа назад в UTC
            from datetime import timezone
            since_date = datetime.now(timezone.utc) - timedelta(hours=24)
            since_str = since_date.strftime('%Y-%m-%d')
            
            # Поиск по ключевым словам
            for keyword in self.config.AI_KEYWORDS[:5]:  # Ограничиваем количество запросов
                try:
                    # Формируем поисковый запрос
                    query = f'"{keyword}" since:{since_str} -filter:retweets lang:en'
                    
                    self.logger.info(f"Поиск твитов с запросом: {query}")
                    
                    scraper = sntwitter.TwitterSearchScraper(query)
                    
                    count = 0
                    for tweet in scraper.get_items():
                        if count >= max_results:
                            break
                        
                        tweet_data = self._extract_tweet_data(tweet)
                        if tweet_data and self._is_valid_tweet(tweet_data):
                            tweets.append(tweet_data)
                            count += 1
                    
                    self.logger.info(f"Найдено {count} твитов для ключевого слова: {keyword}")
                    
                except Exception as e:
                    self.logger.error(f"Ошибка при поиске твитов для '{keyword}': {e}")
                    continue
            
            # Удаляем дубликаты
            tweets = self.filter.remove_duplicates(tweets)
            
            self.logger.info(f"Всего найдено уникальных твитов по ключевым словам: {len(tweets)}")
            return tweets
            
        except Exception as e:
            self.logger.error(f"Ошибка при поиске твитов по ключевым словам: {e}")
            return []
    
    def _extract_tweet_data(self, tweet) -> Dict[str, Any]:
        """Извлекает данные о твите"""
        try:
            # Проверяем, что твит свежий (за последние 24 часа)
            if not self.filter.is_recent_news(tweet.date, 24):
                return None
            
            tweet_data = {
                'title': tweet.content,  # Показываем полный текст твита
                'url': tweet.url,
                'author': tweet.user.username,
                'published_date': tweet.date,
                'source': 'Twitter/X',
                'retweet_count': tweet.retweetCount,
                'like_count': tweet.likeCount,
                'reply_count': tweet.replyCount,
                'keywords': self.filter.extract_keywords_from_text(tweet.content)
            }
            
            return tweet_data
            
        except Exception as e:
            self.logger.error(f"Ошибка при извлечении данных твита: {e}")
            return None
    
    def _is_valid_tweet(self, tweet_data: Dict[str, Any]) -> bool:
        """Проверяет, подходит ли твит для включения в дайджест"""
        if not tweet_data:
            return False
        
        content = tweet_data.get('title', '')
        
        # Проверяем наличие ключевых слов
        if not self.filter.contains_ai_keywords(content):
            return False
        
        # Проверяем, что это не ретвит
        if self.filter.is_retweet(content):
            return False
        
        # Проверяем минимальную длину контента
        if len(content) < 20:
            return False
        
        return True
    
    def get_trending_tweets(self, max_results: int = 30) -> List[Dict[str, Any]]:
        """Получает популярные твиты по теме ИИ"""
        tweets = []
        
        try:
            # Поиск популярных твитов
            since_date = datetime.now() - timedelta(hours=24)
            since_str = since_date.strftime('%Y-%m-%d')
            
            # Комбинированный запрос для популярных твитов
            query = f'(AI OR "artificial intelligence" OR ChatGPT OR OpenAI) since:{since_str} -filter:retweets min_faves:10'
            
            self.logger.info(f"Поиск популярных твитов: {query}")
            
            scraper = sntwitter.TwitterSearchScraper(query)
            
            count = 0
            for tweet in scraper.get_items():
                if count >= max_results:
                    break
                
                tweet_data = self._extract_tweet_data(tweet)
                if tweet_data and self._is_valid_tweet(tweet_data):
                    tweets.append(tweet_data)
                    count += 1
            
            self.logger.info(f"Найдено {len(tweets)} популярных твитов")
            return tweets
            
        except Exception as e:
            self.logger.error(f"Ошибка при получении популярных твитов: {e}")
            return []
