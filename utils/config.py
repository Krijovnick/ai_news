import os
from dotenv import load_dotenv
import logging

# Загружаем переменные окружения
load_dotenv()

# Стартовый набор ключевых слов (засев в SQLite, если active пуст)
SEED_KEYWORDS = [
    "AI automation",
    "AI agents",
    "AI for business",
    "AI use case",
    "AI workflow",
    "online business AI",
    "AI didn't work",
    "AI case study",
    "AI implementation",
    "AI success story",
    "AI failed",
    "AI coding agents",
    "AI tools for developers",
    "ИИ",
    "ИИ-автоматизация",
    "агенты",
    "онлайн-бизнес с ИИ",
    "кейсы внедрения",
    "что получилось и что не получилось",
    "ИИ автоматизация",
    "ИИ для бизнеса",
    "кейс внедрения ИИ",
    "онлайн бизнес с ИИ",
]


class Config:
    """Конфигурация приложения"""

    # Telegram
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

    # DeepSeek
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
    DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    ARTICLES_PER_RUN = int(os.getenv("ARTICLES_PER_RUN", "5"))

    # Reddit API
    REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
    REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
    REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "AI_News_Aggregator/1.0")

    # Флаги источников
    ENABLE_GOOGLE_NEWS = os.getenv("ENABLE_GOOGLE_NEWS", "true").lower() == "true"
    ENABLE_HACKERNEWS = os.getenv("ENABLE_HACKERNEWS", "true").lower() == "true"
    ENABLE_REDDIT = os.getenv("ENABLE_REDDIT", "true").lower() == "true"

    # Логирование
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    # Пути
    DATA_DIR = os.getenv("DATA_DIR", "data")
    DB_PATH = os.getenv("DB_PATH", os.path.join(DATA_DIR, "news.db"))
    PROMPTS_PATH = os.getenv("PROMPTS_PATH", os.path.join("prompts", "deepseek.yaml"))
    WEB_HOST = os.getenv("WEB_HOST", "127.0.0.1")
    WEB_PORT = int(os.getenv("WEB_PORT", "5050"))
    WEB_URL = os.getenv("WEB_URL", f"http://{WEB_HOST}:{WEB_PORT}")

    # Исключаем академию и «пустые» анонсы без практики
    EXCLUDE_KEYWORDS = [
        "research paper",
        "arxiv.org",
        "dataset",
        "loss function",
        "backpropagation",
        "gradient descent",
        "model weights",
        "benchmark leaderboard",
        "training method",
        "ablation study",
        "parameters released",
        "weights released",
    ]

    # AI-сабы Reddit (без общих бизнес-сабов)
    REDDIT_SUBREDDITS = [
        "ChatGPT",
        "ChatGPTCoding",
        "ClaudeAI",
        "OpenAI",
        "Automate",
        "n8n",
        "LocalLLaMA",
        "Artificial",
        "singularity",
        "AI_Agents",
    ]

    # Онлайн-бизнес сабы
    REDDIT_BUSINESS_SUBREDDITS = [
        "indiehackers",
        "SaaS",
        "SideProject",
        "microsaas",
        "Entrepreneur",
        "startups",
        "sidehustle",
        "juststart",
    ]

    # Спам, вакансии, курсы «быстрых денег»
    REDDIT_BUSINESS_EXCLUDE_KEYWORDS = [
        "we're hiring",
        "we are hiring",
        "hiring:",
        "job opening",
        "looking for employees",
        "resume review",
        "looking for a job",
        "job offer",
        "buy my course",
        "my course",
        "coaching call",
        "1:1 coaching",
        "mentorship program",
        "dropshipping course",
        "get rich quick",
        "make money fast",
        "guaranteed income",
        "crypto signal",
        "nft drop",
        "pump and dump",
        "day trading",
        "stock tip",
        "upvote if",
        "free giveaway",
        "onlyfans",
        "fed rate",
        "interest rate hike",
        "stock market crash",
        "recession news",
    ]

    # Явные признаки офлайн-бизнеса
    REDDIT_OFFLINE_KEYWORDS = [
        "brick and mortar",
        "brick-and-mortar",
        "offline business",
        "physical store",
        "physical location",
        "local shop",
        "retail store",
        "restaurant",
        "food truck",
        "lawn care",
        "landscaping",
        "car wash",
        "laundromat",
        "vending machine",
        "sweaty startup",
        "офлайн бизнес",
        "оффлайн бизнес",
        "оффлайн",
        "локальный магазин",
        "кафе",
        "ресторан",
    ]

    REDDIT_BUSINESS_MIN_SCORE = int(os.getenv("REDDIT_BUSINESS_MIN_SCORE", "10"))
    REDDIT_BUSINESS_TOP_PER_SUB = int(os.getenv("REDDIT_BUSINESS_TOP_PER_SUB", "15"))

    NEWS_LOOKBACK_DAYS = int(os.getenv("NEWS_LOOKBACK_DAYS", "7"))
    # Устарело для обрезки дайджеста; оставлено для совместимости env
    DIGEST_MAX_ITEMS = int(os.getenv("DIGEST_MAX_ITEMS", "40"))

    GOOGLE_NEWS_MAX = int(os.getenv("GOOGLE_NEWS_MAX", "60"))
    HACKERNEWS_MAX = int(os.getenv("HACKERNEWS_MAX", "50"))
    REDDIT_AI_MAX = int(os.getenv("REDDIT_AI_MAX", "50"))
    REDDIT_BUSINESS_MAX = int(os.getenv("REDDIT_BUSINESS_MAX", "50"))
    ITEM_TEXT_PROMPT_CHARS = int(os.getenv("ITEM_TEXT_PROMPT_CHARS", "800"))

    PRACTICAL_KEYWORDS = [
        "automat",
        "agent",
        "workflow",
        "n8n",
        "zapier",
        "make.com",
        "business",
        "startup",
        "saas",
        "use case",
        "tutorial",
        "how to",
        "build",
        "productivity",
        "sales",
        "marketing",
        "customer support",
        "revenue",
        "monetiz",
        "indie",
        "side project",
        "freelance",
        "no-code",
        "nocode",
        "playbook",
        "case study",
        "framework",
        "open source",
        "open-source",
        "developer tool",
        "setup",
        "configure",
        "автоматиз",
        "агент",
        "бизнес",
        "стартап",
        "заработ",
        "продаж",
        "маркетинг",
        "как сделать",
        "как внедрить",
        "кейс",
        "настройк",
    ]

    ANNOUNCEMENT_PENALTY_KEYWORDS = [
        "introducing gpt",
        "releases model",
        "new model release",
        "drops model",
        "model weights",
        "weights released",
        "parameters released",
        "frontier model",
        "new llm",
        "анонсировал модель",
        "представил модель",
        "выпустил модель",
    ]

    # Явные маркеры ИИ для бизнес-постов Reddit
    AI_SENSE_MARKERS = [
        "ai",
        "a.i.",
        "ии",
        "нейросет",
        "llm",
        "chatgpt",
        "claude",
        "openai",
        "machine learning",
        "generative",
    ]

    @classmethod
    def validate_config(cls, *, require_telegram: bool = True, require_deepseek: bool = True):
        """Проверяет корректность конфигурации для полного прогона."""
        errors = []

        if require_telegram:
            if not cls.TELEGRAM_BOT_TOKEN:
                errors.append("TELEGRAM_BOT_TOKEN не установлен")
            if not cls.TELEGRAM_CHAT_ID:
                errors.append("TELEGRAM_CHAT_ID не установлен")

        if require_deepseek and not cls.DEEPSEEK_API_KEY:
            errors.append("DEEPSEEK_API_KEY не установлен")

        if cls.ENABLE_REDDIT and (not cls.REDDIT_CLIENT_ID or not cls.REDDIT_CLIENT_SECRET):
            errors.append("Reddit API credentials не установлены, но Reddit включен")

        if errors:
            raise ValueError("Ошибки конфигурации:\n" + "\n".join(errors))

        return True


def setup_logging():
    """Настройка логирования"""
    os.makedirs("logs", exist_ok=True)

    log_level = getattr(logging, Config.LOG_LEVEL.upper(), logging.INFO)

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler("logs/app.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )

    return logging.getLogger(__name__)
