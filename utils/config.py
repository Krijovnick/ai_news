import os
from dotenv import load_dotenv
import logging

# Загружаем переменные окружения
load_dotenv()

class Config:
    """Конфигурация приложения"""
    
    # Telegram настройки
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
    
    # YouTube API
    YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')
    
    # Reddit API
    REDDIT_CLIENT_ID = os.getenv('REDDIT_CLIENT_ID')
    REDDIT_CLIENT_SECRET = os.getenv('REDDIT_CLIENT_SECRET')
    REDDIT_USER_AGENT = os.getenv('REDDIT_USER_AGENT', 'AI_News_Aggregator/1.0')
    
    # Настройки источников
    ENABLE_YOUTUBE = os.getenv('ENABLE_YOUTUBE', 'true').lower() == 'true'
    ENABLE_TWITTER = os.getenv('ENABLE_TWITTER', 'true').lower() == 'true'
    ENABLE_GOOGLE_NEWS = os.getenv('ENABLE_GOOGLE_NEWS', 'true').lower() == 'true'
    ENABLE_HACKERNEWS = os.getenv('ENABLE_HACKERNEWS', 'true').lower() == 'true'
    ENABLE_REDDIT = os.getenv('ENABLE_REDDIT', 'true').lower() == 'true'
    
    # Логирование
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    
    # Ключевые слова для поиска
    AI_KEYWORDS = [
        "AI news", "artificial intelligence", "ChatGPT", "OpenAI", 
        "Claude", "Anthropic", "Gemini AI", "DeepMind", "Sora", 
        "Stable Diffusion", "Midjourney", "Runway AI", "text-to-video", 
        "text-to-image", "LLM", "AI", "OpenAI", "Anthropic", "Google", "DeepMind",
        "Microsoft", "Meta", "NVIDIA", "Adobe", "Stability AI", "Runway", "Jasper AI"
    ]
    
    # Исключаемые слова
    EXCLUDE_KEYWORDS = [
        "paper", "research paper", "dataset", "loss function", 
        "training method", "backpropagation", "gradient descent", 
        "model weights", "benchmark", "arxiv.org"
    ]
    
    # Хэштеги для Twitter
    TWITTER_HASHTAGS = [
        "#ai", "#chatgpt", "#openai", "#artificialintelligence", 
        "#stablediffusion", "#generativeai"
    ]
    
    # Сабреддиты для Reddit
    REDDIT_SUBREDDITS = [
        "MachineLearning", "Artificial", "ChatGPT", "OpenAI", "StableDiffusion"
    ]
    
    @classmethod
    def validate_config(cls):
        """Проверяет корректность конфигурации"""
        errors = []
        
        if not cls.TELEGRAM_BOT_TOKEN:
            errors.append("TELEGRAM_BOT_TOKEN не установлен")
        
        if not cls.TELEGRAM_CHAT_ID:
            errors.append("TELEGRAM_CHAT_ID не установлен")
        
        if cls.ENABLE_YOUTUBE and not cls.YOUTUBE_API_KEY:
            errors.append("YOUTUBE_API_KEY не установлен, но YouTube включен")
        
        if cls.ENABLE_REDDIT and (not cls.REDDIT_CLIENT_ID or not cls.REDDIT_CLIENT_SECRET):
            errors.append("Reddit API credentials не установлены, но Reddit включен")
        
        if errors:
            raise ValueError("Ошибки конфигурации:\n" + "\n".join(errors))
        
        return True

def setup_logging():
    """Настройка логирования"""
    # Создаем директорию для логов
    os.makedirs('logs', exist_ok=True)
    
    # Настройка логирования
    log_level = getattr(logging, Config.LOG_LEVEL.upper(), logging.INFO)
    
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('logs/app.log', encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    
    return logging.getLogger(__name__)
