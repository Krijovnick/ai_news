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
    
    # Reddit API
    REDDIT_CLIENT_ID = os.getenv('REDDIT_CLIENT_ID')
    REDDIT_CLIENT_SECRET = os.getenv('REDDIT_CLIENT_SECRET')
    REDDIT_USER_AGENT = os.getenv('REDDIT_USER_AGENT', 'AI_News_Aggregator/1.0')
    
    # Настройки источников
    ENABLE_TWITTER = os.getenv('ENABLE_TWITTER', 'true').lower() == 'true'
    ENABLE_GOOGLE_NEWS = os.getenv('ENABLE_GOOGLE_NEWS', 'true').lower() == 'true'
    ENABLE_HACKERNEWS = os.getenv('ENABLE_HACKERNEWS', 'true').lower() == 'true'
    ENABLE_REDDIT = os.getenv('ENABLE_REDDIT', 'true').lower() == 'true'
    
    # Логирование
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    
    # Запросы без названий конкретных продуктов: так всплывают новые инструменты,
    # фреймворки и способы автоматизации, а не уже известные темы.
    DISCOVERY_KEYWORDS = [
        "new AI agent tool",
        "new AI developer tool",
        "new AI automation tool",
        "emerging AI agents",
        "open source AI agents",
        "new AI workflow tool",
        "AI tools for developers",
        "новые ИИ инструменты для бизнеса",
        "новый инструмент для ИИ агентов",
    ]

    # Ключевые слова для поиска (практика: автоматизация, агенты, бизнес, заработок)
    AI_KEYWORDS = [
        # Агенты и автоматизация
        "AI agents", "AI agent", "autonomous agents", "multi-agent",
        "AI automation", "business automation", "workflow automation",
        "AI workflows", "n8n automation", "Zapier AI", "Make.com AI",
        # Бизнес и применение
        "AI for business", "AI for startups", "AI use cases",
        "AI for sales", "AI for marketing", "AI customer support",
        "AI productivity", "AI operations", "AI SaaS",
        # Создание продукта и монетизация
        "build AI SaaS", "AI startup ideas", "AI micro SaaS",
        "indie hacker AI", "AI side project", "monetize with AI",
        "AI coding agents", "Claude Code", "Cursor AI", "vibe coding",
        "AI developer tools",
        # Новые инструменты в разработке и автоматизации — без имён продуктов
        "new AI agent tool", "new AI developer tool", "new AI automation tool",
        "emerging AI agents", "open source AI agents", "agent framework",
        "AI tools for developers", "AI agent setup", "configuring AI agents",
        # Русскоязычные
        "ИИ агенты", "ИИ автоматизация", "автоматизация бизнеса",
        "ИИ для бизнеса", "нейросети для бизнеса", "ИИ стартап",
        "ИИ для продаж", "ИИ для маркетинга", "заработок на ИИ",
        "настройка ИИ агентов", "новые ИИ инструменты", "ИИ агенты для разработки",
    ]

    # Исключаем академию и «пустые» анонсы без практики
    EXCLUDE_KEYWORDS = [
        "research paper", "arxiv.org", "dataset", "loss function",
        "backpropagation", "gradient descent", "model weights",
        "benchmark leaderboard", "training method", "ablation study",
        "parameters released", "weights released",
    ]

    # Хэштеги для Twitter
    TWITTER_HASHTAGS = [
        "#AIagents", "#AIautomation", "#buildinpublic",
        "#indiehacker", "#SaaS", "#n8n", "#ChatGPT",
    ]

    # Сабреддиты: больше практики и бизнеса, меньше чистого research-hype
    REDDIT_SUBREDDITS = [
        "ChatGPT", "ChatGPTCoding", "ClaudeAI", "OpenAI",
        "Automate", "n8n", "LocalLLaMA",
        "SaaS", "indiehackers", "startups", "Entrepreneur",
        "Artificial", "singularity",
        # Здесь чаще всего постят новые агентные инструменты, без привязки к одному продукту
        "AI_Agents",
    ]

    # Сабреддиты для --reddit-business: идеи, истории запуска, side projects (не общая бизнес-пресса)
    REDDIT_BUSINESS_SUBREDDITS = [
        "startup_ideas", "Business_Ideas", "startupideas", "SomebodyMakeThis", "AppIdeas",
        "SideProject", "indiehackers", "SaaS", "microsaas", "sweatystartup", "juststart",
        "EntrepreneurRideAlong", "Entrepreneur", "startups", "smallbusiness", "Entrepreneurship",
        "sidehustle", "EntrepreneurUK", "EntrepreneurshipStudents", "alphaandbetausers",
    ]

    # Сабы, где почти всё — идеи: достаточно отсутствия спама (без жёсткого keyword-match)
    REDDIT_BUSINESS_IDEA_SUBREDDITS = {
        "startup_ideas", "business_ideas", "startupideas", "somebodymakethis",
        "appideas", "sideproject", "alphaandbetausers",
    }

    # Идеи / истории создания / решаемые проблемы (онлайн и оффлайн)
    REDDIT_BUSINESS_IDEA_KEYWORDS = [
        "business idea", "startup idea", "app idea", "saas idea", "product idea",
        "side hustle idea", "side project", "niche idea", "service idea",
        "idea:", "[idea]", "[ideas]", "idea for", "ideas for",
        "somebody make", "would anyone pay", "would you pay", "looking for feedback",
        "validate", "validation", "pain point", "problem i", "problem we",
        "solved a problem", "solving a problem", "customer problem", "market gap",
        "i built", "i launched", "i started", "i founded", "i created", "i made a",
        "we built", "we launched", "we started", "how i built", "how i started",
        "how we built", "how i made", "my journey", "founder story", "origin story",
        "case study", "lessons learned", "from 0 to", "from idea to", "bootstrapped",
        "started a business", "built a business", "launched a", "launched my",
        "first customer", "first sale", "first clients", "hit $", "mrr", "arr",
        "revenue update", "making money with", "turned into a business",
        "offline business", "online business", "local business", "brick and mortar",
        "ecommerce store", "e-commerce", "agency", "freelance business",
        "what if", "unmet need", "underserved", "mvp", "build in public",
        "бизнес идея", "идея для бизнеса", "стартап идея", "запустил бизнес",
        "создал бизнес", "история запуска", "как я запустил", "решил проблему",
        "идея приложения", "side hustle",
    ]

    # Спам, вакансии, курсы «быстрых денег», общая финансовая пресса
    REDDIT_BUSINESS_EXCLUDE_KEYWORDS = [
        "we're hiring", "we are hiring", "hiring:", "job opening", "looking for employees",
        "resume review", "looking for a job", "job offer",
        "buy my course", "my course", "coaching call", "1:1 coaching", "mentorship program",
        "dropshipping course", "get rich quick", "make money fast", "guaranteed income",
        "crypto signal", "nft drop", "pump and dump", "day trading", "stock tip",
        "upvote if", "free giveaway", "onlyfans",
        "fed rate", "interest rate hike", "stock market crash", "recession news",
    ]

    # Минимум апвотов — идеи, которые уже «зашли» людям
    REDDIT_BUSINESS_MIN_SCORE = int(os.getenv("REDDIT_BUSINESS_MIN_SCORE", "10"))

    # Сколько топовых постов за неделю брать с каждого саба (потом режем по max_results)
    REDDIT_BUSINESS_TOP_PER_SUB = int(os.getenv("REDDIT_BUSINESS_TOP_PER_SUB", "15"))

    # Период и метрики "топа" для дайджеста
    NEWS_LOOKBACK_DAYS = int(os.getenv("NEWS_LOOKBACK_DAYS", "7"))
    # Сколько материалов с наивысшим рейтингом уходит в Telegram
    DIGEST_MAX_ITEMS = int(os.getenv("DIGEST_MAX_ITEMS", "40"))

    # Сигналы «можно применить в бизнесе / для заработка» (скоринг)
    PRACTICAL_KEYWORDS = [
        "automat", "agent", "workflow", "n8n", "zapier", "make.com",
        "business", "startup", "saas", "use case", "tutorial", "how to",
        "build", "productivity", "sales", "marketing", "customer support",
        "revenue", "monetiz", "indie", "side project", "freelance",
        "no-code", "nocode", "playbook", "case study",
        "framework", "open source", "open-source", "developer tool",
        "setup", "configure",
        "автоматиз", "агент", "бизнес", "стартап", "заработ", "продаж",
        "маркетинг", "как сделать", "как внедрить", "кейс", "настройк",
    ]

    # Штраф только за анонсы моделей. Запуск нового инструмента или фреймворка не режем:
    # как раз так находятся технологии, которых ещё нет в списке ключевых слов.
    ANNOUNCEMENT_PENALTY_KEYWORDS = [
        "introducing gpt", "releases model", "new model release",
        "drops model", "model weights", "weights released",
        "parameters released", "frontier model", "new llm",
        "анонсировал модель", "представил модель", "выпустил модель",
    ]
    
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
