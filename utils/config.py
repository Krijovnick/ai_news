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
    
    # Провайдер суммаризации: gemini | deepseek | openrouter
    SUMMARIZER_PROVIDER = os.getenv('SUMMARIZER_PROVIDER', 'gemini').lower()

    # Gemini / Google AI
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
    GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-2.5-flash')
    # Ограничиваем частоту запросов, чтобы не упираться в лимит free tier (5 rpm)
    GEMINI_REQUESTS_PER_MINUTE = int(os.getenv('GEMINI_REQUESTS_PER_MINUTE', '4'))

    # DeepSeek (OpenAI-совместимое API)
    DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
    DEEPSEEK_MODEL = os.getenv('DEEPSEEK_MODEL', 'deepseek-chat')
    DEEPSEEK_REQUESTS_PER_MINUTE = int(os.getenv('DEEPSEEK_REQUESTS_PER_MINUTE', '8'))

    # OpenRouter (OpenAI-совместимое API, можно проксировать DeepSeek)
    OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
    OPENROUTER_MODEL = os.getenv('OPENROUTER_MODEL', 'deepseek/deepseek-chat')
    OPENROUTER_BASE_URL = os.getenv('OPENROUTER_BASE_URL', 'https://openrouter.ai/api/v1')
    OPENROUTER_REQUESTS_PER_MINUTE = int(os.getenv('OPENROUTER_REQUESTS_PER_MINUTE', '8'))

    # Включать ли вообще ИИ-суммаризацию (если false — шлём новости без выжимок)
    ENABLE_SUMMARIZER = os.getenv('ENABLE_SUMMARIZER', 'true').lower() == 'true'
    
    # Reddit API
    REDDIT_CLIENT_ID = os.getenv('REDDIT_CLIENT_ID')
    REDDIT_CLIENT_SECRET = os.getenv('REDDIT_CLIENT_SECRET')
    REDDIT_USER_AGENT = os.getenv('REDDIT_USER_AGENT', 'AI_News_Aggregator/1.0')
    
    # Настройки источников
    ENABLE_TWITTER = os.getenv('ENABLE_TWITTER', 'true').lower() == 'true'
    ENABLE_GOOGLE_NEWS = os.getenv('ENABLE_GOOGLE_NEWS', 'true').lower() == 'true'
    ENABLE_HACKERNEWS = os.getenv('ENABLE_HACKERNEWS', 'true').lower() == 'true'
    ENABLE_REDDIT = os.getenv('ENABLE_REDDIT', 'true').lower() == 'true'
    ENABLE_YOUTUBE = os.getenv('ENABLE_YOUTUBE', 'true').lower() == 'true'
    
    # Логирование
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    
    # Ключевые слова для поиска
    AI_KEYWORDS = [
        "AI automation", "AI workflows", "AI for developers", "AI for startups", 
        "AI business automation", "AI use cases", "AI agents", "AI coding tools", 
        "AI developer tools", "AI productivity tools", "vibe coding", "Flux workflow", 
        "Midjourney", "ComfyUI workflow", "AI thumbnails", "AI short videos", 
        "AI reels automation", "AI YouTube automation", "AI reels workflow", 
        "multi-agent systems", "AI research agents", "ИИ автоматизация", "AI автоматизация бизнеса", "ИИ для программистов", "ИИ для разработки", 
        "AI инструменты", "ИИ для продуктивности", "AI дизайн", "AI для соцсетей", "AI агенты",
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
    
    # Сабреддиты для Reddit (дайджест об ИИ)
    REDDIT_SUBREDDITS = [
        "MachineLearning", "Artificial", "ChatGPT", "OpenAI", "StableDiffusion",
        "ClaudeAI", "singularity", "comfyui", "ChatGPTCoding", "Automate",
    ]

    # Сабреддиты для отдельного бизнес-дайджеста (команда --reddit-business)
    REDDIT_BUSINESS_SUBREDDITS = [
        "Entrepreneur", "startups", "smallbusiness", "business", "EntrepreneurRideAlong",
        "SideProject", "startup_ideas", "Business_Ideas", "Entrepreneurship", "Ideas",
        "SomebodyMakeThis", "AppIdeas", "SaaS", "microsaas", "indiehackers",
        "passive_income", "sidehustle", "WorkOnline", "digitalnomad", "ecommerce",
        "dropshipping", "Affiliatemarketing", "juststart", "sweatystartup", "EntrepreneurUK",
        "growthhacking", "marketing", "freelance", "startupideas", "EntrepreneurshipStudents",
    ]

    # Минимум апвотов, чтобы отсечь совсем незаметные посты
    REDDIT_BUSINESS_MIN_SCORE = int(os.getenv("REDDIT_BUSINESS_MIN_SCORE", "5"))

    # Сколько «топовых за день» постов запрашивать с каждого саба (потом режем по max_results)
    REDDIT_BUSINESS_TOP_PER_SUB = int(os.getenv("REDDIT_BUSINESS_TOP_PER_SUB", "12"))

    # Период и метрики "топа" для дайджеста
    NEWS_LOOKBACK_DAYS = int(os.getenv("NEWS_LOOKBACK_DAYS", "7"))
    YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
    YOUTUBE_MAX_RESULTS_PER_QUERY = int(os.getenv("YOUTUBE_MAX_RESULTS_PER_QUERY", "12"))
    YOUTUBE_MIN_VIEWS = int(os.getenv("YOUTUBE_MIN_VIEWS", "50000"))
    
    @classmethod
    def validate_config(cls):
        """Проверяет корректность конфигурации"""
        errors = []
        
        if not cls.TELEGRAM_BOT_TOKEN:
            errors.append("TELEGRAM_BOT_TOKEN не установлен")
        
        if not cls.TELEGRAM_CHAT_ID:
            errors.append("TELEGRAM_CHAT_ID не установлен")
        
        if cls.ENABLE_REDDIT and (not cls.REDDIT_CLIENT_ID or not cls.REDDIT_CLIENT_SECRET):
            errors.append("Reddit API credentials не установлены, но Reddit включен")

        if cls.ENABLE_YOUTUBE and not cls.YOUTUBE_API_KEY:
            errors.append("YOUTUBE_API_KEY не установлен, но YouTube включен")

        if not cls.GEMINI_API_KEY:
            errors.append("GEMINI_API_KEY не установлен (нужен для генерации выжимок статей)")
        
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
