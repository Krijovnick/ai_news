# AI News Aggregator

Недельный сбор материалов про ИИ, разбор и статьи через DeepSeek в SQLite, чтение на локальном сайте. Что программа должна делать — в [базе знаний](docs/knowledge-base/README.md).

## Запуск двойным кликом (Windows)

| Файл | Что делает |
|------|------------|
| `Collect.bat` | Полный недельный прогон (`python main.py`). |
| `Web.bat` | Сайт `http://127.0.0.1:5050` (`python web.py`). |

Окно консоли остаётся открытым до нажатия клавиши.

## Команды

Запускать из корня проекта с настроенным `.env`.

| Команда | Что делает |
|--------|------------|
| `python main.py` | Полный прогон: сбор за последние `NEWS_LOOKBACK_DAYS` дней, фильтр, DeepSeek, запись в `data/news.db`, одно уведомление в Telegram. |
| `python main.py --test` | Проверка источников без Telegram и без записи разбора в базу. |
| `python web.py` | Веб-интерфейс разборов и ключевых слов на `http://127.0.0.1:5050`. |
| `python test_aggregator.py` | Локальные проверки без сети и боевого Telegram. |
| `python install.py` | Зависимости и каталоги `logs`, `data`. |

Интерфейс на Vue; пересборка — `npm run build` в каталоге `frontend/`.

Неизвестный аргумент `main.py` завершает процесс с кодом 2, без сбора.

## Переменные окружения

Секреты и флаги задаются в `.env` (имена в `utils/config.py`): Telegram, Reddit, `DEEPSEEK_API_KEY`, `DEEPSEEK_MODEL`, `ARTICLES_PER_RUN`, `ARTICLE_ITEM_TEXT_CHARS`, `DEEPSEEK_WEB_TOOLS`, `ARTICLE_SEARCH_RESULTS`, `ENABLE_*` для источников.

## Логи и данные

- Логи: `logs/app.log`
- База: `data/` (в `.gitignore`)
