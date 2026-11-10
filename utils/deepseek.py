"""Клиент DeepSeek Chat Completions API."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlsplit

import requests
import yaml

from utils.config import Config

logger = logging.getLogger(__name__)

API_URL = "https://api.deepseek.com/v1/chat/completions"
CHUNK_SIZE = 25
# И плану, и статье даём максимум вывода deepseek-chat.
PLAN_MAX_TOKENS = 8192
ARTICLE_MAX_TOKENS = 8192
CHAT_TIMEOUT = 300

# Повторы chat/completions при временных сбоях (обрыв, соединение, таймаут, 429, 5xx):
# по одной паузе на повтор, т.е. 2 повтора после первой попытки.
CHAT_RETRY_DELAYS: Tuple[float, ...] = (5, 15)
# Потолок паузы из Retry-After для 429 (секунды или HTTP-date), секунды.
CHAT_RETRY_AFTER_MAX = 60
# Неразобранный ответ плана или статьи (не JSON, нет полей): всего попыток (1 повтор).
UNPARSED_ATTEMPTS = 2
# Сколько символов сырого ответа с начала и с конца писать в лог при неразборе.
RAW_LOG_EDGE_CHARS = 300

# Search/Fetch API DeepSeek: полные тексты и дополнительные источники для статьи.
FETCH_URL = "https://api.deepseek.com/v1/tools/fetch"
SEARCH_URL = "https://api.deepseek.com/v1/tools/search"
TOOLS_TIMEOUT = 60
SEARCH_MIN_RERANK = 1.5
SEARCH_QUERY_MAX_CHARS = 128
MAX_SEARCH_QUERIES = 2
# Fetch API DeepSeek не загружает Reddit (стабильно 404 на /v1/tools/fetch), а текст
# поста уже есть из PRAW: для этих хостов и их поддоменов fetch не вызывается.
FETCH_SKIP_HOSTS: Tuple[str, ...] = ("reddit.com", "redd.it")

# Обязательные секции/ключи PROMPTS_PATH — без текстов инструкций (источник текстов — YAML).
_REQUIRED_PROMPT_KEYS: Dict[str, Tuple[str, ...]] = {
    "weekly_analysis": (
        "system_single",
        "system_partial",
        "system_merge",
        "user_single",
        "user_partial",
        "user_merge",
        "partials_joiner",
    ),
    "articles_and_keywords": (
        "author",
        "plan_system",
        "plan_user",
        "write_system",
        "write_user",
    ),
}

_prompts_cache: Optional[Dict[str, Any]] = None
_prompts_cache_path: Optional[str] = None


class PromptsLoadError(Exception):
    """Файл промптов DeepSeek отсутствует, повреждён или невалиден."""


def _fill(template: str, **kwargs: Any) -> str:
    """Подставляет плейсхолдеры вида {name} без интерпретации прочих фигурных скобок."""
    result = template
    for key, value in kwargs.items():
        result = result.replace("{" + key + "}", str(value))
    return result


def _validate_prompts(data: Dict[str, Any]) -> Dict[str, Any]:
    """Проверяет полноту схемы ключей; тексты инструкций в коде не хранятся."""
    prompts: Dict[str, Any] = {}
    problems: List[str] = []
    for section, keys in _REQUIRED_PROMPT_KEYS.items():
        loaded = data.get(section)
        if not isinstance(loaded, dict):
            problems.append(f"{section} (секция отсутствует или не mapping)")
            continue
        section_out: Dict[str, Any] = {}
        for key in keys:
            if key not in loaded or loaded[key] is None:
                problems.append(f"{section}.{key}")
                continue
            value = loaded[key]
            if not isinstance(value, str):
                problems.append(f"{section}.{key} (ожидалась строка)")
                continue
            # partials_joiner хранит значимые \n — не strip.
            if key != "partials_joiner":
                value = value.strip()
                if not value:
                    problems.append(f"{section}.{key} (пустая строка)")
                    continue
            section_out[key] = value
        prompts[section] = section_out
    if problems:
        raise PromptsLoadError(
            "неполная или невалидная структура: " + ", ".join(problems)
        )
    return prompts


def clear_prompts_cache() -> None:
    """Сбрасывает кэш промптов (для тестов и смены PROMPTS_PATH)."""
    global _prompts_cache, _prompts_cache_path
    _prompts_cache = None
    _prompts_cache_path = None


def load_prompts(path: Optional[str] = None) -> Dict[str, Any]:
    """Читает единый файл промптов DeepSeek. Без валидного файла — ошибка (без запасных текстов)."""
    global _prompts_cache, _prompts_cache_path
    path = path or Config.PROMPTS_PATH
    if _prompts_cache is not None and _prompts_cache_path == path:
        return _prompts_cache

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise PromptsLoadError("корень файла должен быть YAML mapping")
        prompts = _validate_prompts(data)
    except FileNotFoundError:
        msg = f"Файл промптов DeepSeek не найден: {path}"
        logger.error(msg)
        raise PromptsLoadError(msg) from None
    except PromptsLoadError as exc:
        msg = f"Невалидные промпты DeepSeek ({path}): {exc}"
        logger.error(msg)
        raise PromptsLoadError(msg) from None
    except Exception as exc:
        msg = f"Не удалось прочитать промпты DeepSeek ({path}): {exc}"
        logger.error(msg)
        raise PromptsLoadError(msg) from exc

    _prompts_cache = prompts
    _prompts_cache_path = path
    return prompts


def load_author_prompt(path: Optional[str] = None) -> str:
    """Голос автора из единого файла промптов (для совместимости и тестов)."""
    prompts = load_prompts(path)
    return str(prompts["articles_and_keywords"]["author"]).strip()


def format_items_for_prompt(
    items: Sequence[Dict[str, Any]],
    max_text_chars: Optional[int] = None,
) -> str:
    max_chars = max_text_chars or Config.ITEM_TEXT_PROMPT_CHARS
    blocks = []
    for i, item in enumerate(items, 1):
        title = item.get("title") or ""
        source = item.get("source") or ""
        url = item.get("url") or ""
        text = (item.get("description") or item.get("text") or "")[:max_chars]
        blocks.append(
            f"{i}. [{source}] {title}\nURL: {url}\nТекст: {text}"
        )
    return "\n\n".join(blocks)


class DeepSeekClient:
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or Config.DEEPSEEK_API_KEY
        self.model = model or Config.DEEPSEEK_MODEL
        if not self.api_key:
            raise ValueError("DEEPSEEK_API_KEY не установлен")
        self.last_finish_reason: Optional[str] = None

    def _chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        step: str = "запрос DeepSeek",
        json_mode: bool = False,
    ) -> str:
        """Текст ответа модели. finish_reason последнего ответа — в self.last_finish_reason.

        json_mode=True включает JSON-режим DeepSeek (response_format json_object): для плана
        и статьи. Для разбора недели не включается — там нужен обычный текст.
        """
        self.last_finish_reason = None
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        response = self._post_chat_with_retry(payload, step)
        data = response.json()
        choice = data["choices"][0]
        self.last_finish_reason = choice.get("finish_reason")
        if choice.get("finish_reason") == "length":
            logger.warning(
                "Ответ DeepSeek обрезан по max_tokens (%s)", max_tokens or "по умолчанию"
            )
        # content может прийти null — отдаём пустую строку, разбор решит дальше.
        return (choice["message"].get("content") or "").strip()

    def _log_unparsed(self, step: str, raw: str, attempt: int) -> None:
        """WARNING про неразобранный ответ модели: finish_reason, длина, начало и конец текста."""
        tail = (
            f"повторяю запрос (попытка {attempt + 1} из {UNPARSED_ATTEMPTS})"
            if attempt < UNPARSED_ATTEMPTS
            else "попытки исчерпаны"
        )
        logger.warning(
            "DeepSeek, %s: ответ не разобран (не JSON-объект или нет обязательных полей; попытка %s из %s, finish_reason=%s, "
            "длина %s симв.), %s. Ответ: %s",
            step,
            attempt,
            UNPARSED_ATTEMPTS,
            getattr(self, "last_finish_reason", None),
            len(raw or ""),
            tail,
            _raw_excerpt(raw),
        )

    def _post_chat_with_retry(self, payload: Dict[str, Any], step: str) -> requests.Response:
        """POST chat/completions с повтором временных сбоев; прочие ошибки — сразу наверх.

        Повторяются обрыв ответа, ошибка соединения, таймаут, HTTP 429 и 5xx.
        Остальные 4xx (400, 401, 402 …), SSLError и ProxyError не повторяются. После исчерпания попыток
        пробрасывается последняя ошибка.
        """
        attempts = len(CHAT_RETRY_DELAYS) + 1
        for attempt in range(1, attempts + 1):
            try:
                response = requests.post(
                    API_URL,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=CHAT_TIMEOUT,
                )
                response.raise_for_status()
                return response
            except requests.RequestException as exc:
                retryable, retry_after = _retry_info(exc)
                if not retryable or attempt >= attempts:
                    raise
                delay = CHAT_RETRY_DELAYS[attempt - 1]
                if retry_after is not None:
                    delay = max(delay, min(retry_after, CHAT_RETRY_AFTER_MAX))
                logger.warning(
                    "DeepSeek, %s: попытка %s из %s не удалась (%s), повтор через %s с",
                    step,
                    attempt,
                    attempts,
                    exc,
                    delay,
                )
                time.sleep(delay)
        raise RuntimeError("недостижимо")  # pragma: no cover

    def _chunk_items(self, items: Sequence[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        items = list(items)
        if not items:
            return []
        return [items[i : i + CHUNK_SIZE] for i in range(0, len(items), CHUNK_SIZE)]

    def build_weekly_analysis(self, items: Sequence[Dict[str, Any]]) -> str:
        chunks = self._chunk_items(items)
        if not chunks:
            return ""

        prompts = load_prompts()["weekly_analysis"]

        if len(chunks) == 1:
            prompt = _fill(
                prompts["user_single"],
                materials=format_items_for_prompt(chunks[0]),
            )
            return self._chat(
                [
                    {"role": "system", "content": prompts["system_single"]},
                    {"role": "user", "content": prompt},
                ],
                step="разбор недели",
            )

        partials = []
        total = len(chunks)
        for idx, chunk in enumerate(chunks, 1):
            prompt = _fill(
                prompts["user_partial"],
                idx=idx,
                total=total,
                materials=format_items_for_prompt(chunk),
            )
            partials.append(
                self._chat(
                    [
                        {"role": "system", "content": prompts["system_partial"]},
                        {"role": "user", "content": prompt},
                    ],
                    step=f"разбор недели, часть {idx} из {total}",
                )
            )

        joiner = prompts.get("partials_joiner") or "\n\n---\n\n"
        merge_prompt = _fill(
            prompts["user_merge"],
            partials=joiner.join(partials),
        )
        return self._chat(
            [
                {"role": "system", "content": prompts["system_merge"]},
                {"role": "user", "content": merge_prompt},
            ],
            step="склейка разбора недели",
        )

    def build_articles_and_keywords(
        self,
        items: Sequence[Dict[str, Any]],
        summary: str,
        *,
        recent_titles: Optional[Sequence[str]] = None,
        articles_per_run: Optional[int] = None,
        author_prompt: Optional[str] = None,
        web_tools: Optional[bool] = None,
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """План тем по заголовкам (дубли, ранжирование, топ), сбор текстов, статья на тему."""
        items = list(items)
        limit = articles_per_run if articles_per_run is not None else Config.ARTICLES_PER_RUN
        use_web = Config.DEEPSEEK_WEB_TOOLS if web_tools is None else web_tools
        prompts = load_prompts()["articles_and_keywords"]
        author = author_prompt if author_prompt is not None else prompts["author"]

        titles = [t.strip() for t in (recent_titles or []) if t and t.strip()]
        plan_prompt = _fill(
            prompts["plan_user"],
            limit=limit if limit > 0 else "без ограничения",
            recent_titles="\n".join(f"- {t}" for t in titles) or "(нет)",
            summary=summary,
            materials=format_titles_for_plan(items),
        )
        # Ошибка запроса плана (после повторов в _chat) пробрасывается: без плана статей нет.
        # Неразобранный ответ плана — один повтор запроса (без плана пропадают все статьи).
        plan_messages = [
            {"role": "system", "content": prompts["plan_system"]},
            {"role": "user", "content": plan_prompt},
        ]
        for attempt in range(1, UNPARSED_ATTEMPTS + 1):
            raw_plan = self._chat(
                plan_messages,
                temperature=0.3,
                max_tokens=PLAN_MAX_TOKENS,
                step="план статей",
                json_mode=True,
            )
            if _load_plan_object(raw_plan) is not None:
                break
            self._log_unparsed("план статей", raw_plan, attempt)
        topics, keywords = _parse_plan_payload(raw_plan, item_count=len(items))
        if limit > 0:
            topics = topics[:limit]
        _log_selected_topics(topics, items)

        articles: List[Dict[str, Any]] = []
        for topic in topics:
            topic_items = [items[i] for i in topic["item_indexes"]]
            materials, extras = self._collect_topic_texts(
                topic_items, topic["search_queries"], use_web=use_web
            )
            write_prompt = _fill(
                prompts["write_user"],
                author=author,
                topic=topic["topic"],
                angle=topic["angle"],
                why_together=topic["why_together"],
                materials=format_article_materials(materials),
                extra_sources=format_extra_sources(extras),
            )
            write_messages = [
                {"role": "system", "content": prompts["write_system"]},
                {"role": "user", "content": write_prompt},
            ]
            step = f"статья «{topic['topic']}»"
            article: Optional[Dict[str, Any]] = None
            failed = False
            # Неразобранный ответ статьи — один повтор запроса; ошибка запроса — без повтора
            # здесь (временные сбои уже повторены в _chat).
            for attempt in range(1, UNPARSED_ATTEMPTS + 1):
                try:
                    raw_article = self._chat(
                        write_messages,
                        temperature=0.8,
                        max_tokens=ARTICLE_MAX_TOKENS,
                        step=step,
                        json_mode=True,
                    )
                # Сеть/HTTP-ошибка (после повторов в _chat) или битая структура ответа —
                # пропускаем только эту статью.
                except (
                    requests.RequestException,
                    KeyError,
                    IndexError,
                    TypeError,
                    AttributeError,
                    ValueError,
                ) as exc:
                    logger.error("Статья «%s» не написана: %s", topic["topic"], exc)
                    failed = True
                    break
                article = _parse_article_payload(raw_article)
                if article is not None:
                    break
                self._log_unparsed(step, raw_article, attempt)
            if failed:
                continue
            if article is None:
                logger.error("Статья «%s»: ответ DeepSeek не разобран", topic["topic"])
                continue
            # Ссылки — из материалов темы и переданных в запрос результатов поиска,
            # а не из ответа модели: выдуманных не будет.
            article["source_urls"] = _item_urls(list(topic_items) + extras)
            articles.append(article)
        return articles, keywords

    # --- Сбор текстов для статьи (Search/Fetch API DeepSeek) ---

    def _tool_post(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=TOOLS_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("ответ не JSON-объект")
        return data

    def _fetch_text(self, url: str) -> str:
        """Полный текст страницы (Markdown); пустая строка при любой ошибке."""
        try:
            data = self._tool_post(FETCH_URL, {"url": url})
            content = str(data.get("content") or "").strip()
        except (requests.RequestException, ValueError, TypeError, AttributeError) as exc:
            logger.warning("Fetch DeepSeek не удался для %s: %s", url, exc)
            return ""
        if not content:
            logger.warning("Fetch DeepSeek: пустой текст для %s", url)
            return ""
        return content[: Config.ARTICLE_ITEM_TEXT_CHARS]

    def _search(self, query: str, exclude_urls: set) -> List[Dict[str, Any]]:
        """Результаты поиска с rerank_score >= порога, без URL из exclude_urls (пополняется)."""
        limit = max(Config.ARTICLE_SEARCH_RESULTS, 0)
        if limit == 0:
            return []
        try:
            data = self._tool_post(
                SEARCH_URL,
                {
                    "query": query[:SEARCH_QUERY_MAX_CHARS],
                    # С запасом: часть результатов отсеется по rerank_score и дублям.
                    "count": min(max(limit * 3, 10), 50),
                    "need_content": True,
                },
            )
            raw_results = data.get("results")
            if not isinstance(raw_results, list):
                raise ValueError("в ответе нет списка results")
        except (requests.RequestException, ValueError, TypeError, AttributeError) as exc:
            logger.warning("Search DeepSeek не удался для «%s»: %s", query, exc)
            return []
        results: List[Dict[str, Any]] = []
        for r in raw_results:
            if len(results) >= limit:
                break
            if not isinstance(r, dict):
                continue
            try:
                score = float(r.get("rerank_score"))
            except (TypeError, ValueError):
                continue
            url = str(r.get("url") or "").strip()
            if score < SEARCH_MIN_RERANK or not url or url in exclude_urls:
                continue
            text = str(r.get("content") or "").strip() or str(r.get("summary") or "").strip()
            if not text:
                continue
            exclude_urls.add(url)
            results.append(
                {
                    "title": str(r.get("title") or "").strip(),
                    "url": url,
                    "text": text[: Config.ARTICLE_ITEM_TEXT_CHARS],
                }
            )
        if not results:
            # Не сбой: поиск ответил, но всё отсеялось по rerank_score или дублям.
            logger.info("Search DeepSeek: нет подходящих результатов для «%s»", query)
        return results

    def _collect_topic_texts(
        self,
        topic_items: Sequence[Dict[str, Any]],
        search_queries: Sequence[str],
        *,
        use_web: bool,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Материалы темы (текст RSS + полный текст по URL) и дополнительные источники из поиска."""
        materials: List[Dict[str, Any]] = []
        for item in topic_items:
            url = str(item.get("url") or "").strip()
            rss_text = item.get("description") or item.get("text") or ""
            need_fetch = use_web and bool(url)
            if need_fetch and _skip_fetch(url):
                logger.debug("Fetch DeepSeek пропущен для Reddit: %s", url)
                need_fetch = False
            materials.append(
                {
                    "title": item.get("title") or "",
                    "source": item.get("source") or "",
                    "url": url,
                    "text": rss_text[: Config.ARTICLE_ITEM_TEXT_CHARS],
                    "full_text": self._fetch_text(url) if need_fetch else "",
                }
            )
        extras: List[Dict[str, Any]] = []
        if use_web:
            seen = {m["url"] for m in materials if m["url"]}
            for query in search_queries:
                extras.extend(self._search(query, seen))
        return materials, extras


def _skip_fetch(url: str) -> bool:
    """URL на хосте из FETCH_SKIP_HOSTS или его поддомене (по распарсенному хосту)."""
    try:
        host = (urlsplit(url).hostname or "").lower().rstrip(".")
    except ValueError:
        return False
    return any(host == h or host.endswith("." + h) for h in FETCH_SKIP_HOSTS)


def _retry_info(exc: requests.RequestException) -> Tuple[bool, Optional[float]]:
    """Временный ли сбой chat/completions и пауза из Retry-After (для 429), если есть."""
    if isinstance(exc, requests.HTTPError):
        response = exc.response
        status = getattr(response, "status_code", None)
        if status == 429:
            return True, _parse_retry_after(response)
        return isinstance(status, int) and 500 <= status < 600, None
    # SSLError и ProxyError наследуют ConnectionError, но это ошибки настройки
    # (сертификаты, адрес/доступ прокси): за 20 с паузы не исправятся. Проверка раньше.
    if isinstance(exc, (requests.exceptions.SSLError, requests.exceptions.ProxyError)):
        return False, None
    # ChunkedEncodingError — обрыв посреди ответа; ConnectionError и Timeout — сеть.
    if isinstance(
        exc,
        (requests.exceptions.ChunkedEncodingError, requests.ConnectionError, requests.Timeout),
    ):
        return True, None
    return False, None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_retry_after(response: Any) -> Optional[float]:
    """Retry-After в секундах или HTTP-date; None — нет, некорректно или в прошлом."""
    try:
        raw = response.headers.get("Retry-After")
    except AttributeError:
        return None
    if raw is None:
        return None
    text = str(raw).strip()
    try:
        value = float(text)
    except ValueError:
        try:
            when = parsedate_to_datetime(text)
        except (TypeError, ValueError, IndexError):
            return None
        if when is None:
            return None
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        value = (when - _utc_now()).total_seconds()
        return value if value > 0 else None
    return value if value >= 0 else None


def format_titles_for_plan(items: Sequence[Dict[str, Any]]) -> str:
    """Для плана — только номер, источник и заголовок (без текста материала)."""
    return "\n".join(
        f"{i}. [{item.get('source') or ''}] {item.get('title') or ''}"
        for i, item in enumerate(items, 1)
    )


def format_article_materials(materials: Sequence[Dict[str, Any]]) -> str:
    blocks = []
    for i, m in enumerate(materials, 1):
        block = (
            f"{i}. [{m['source']}] {m['title']}\nURL: {m['url'] or '(нет)'}\n"
            f"Текст из источника: {m['text'] or '(нет)'}"
        )
        if m.get("full_text"):
            block += f"\nПолный текст страницы:\n{m['full_text']}"
        blocks.append(block)
    return "\n\n".join(blocks)


def format_extra_sources(extras: Sequence[Dict[str, Any]]) -> str:
    if not extras:
        return "(нет)"
    return "\n\n".join(
        f"{i}. {e['title']}\nURL: {e['url']}\nТекст: {e['text']}"
        for i, e in enumerate(extras, 1)
    )


def _log_selected_topics(
    topics: Sequence[Dict[str, Any]], items: Sequence[Dict[str, Any]]
) -> None:
    logger.info("Тем для статей: %s", len(topics))
    for n, topic in enumerate(topics, 1):
        lines = [
            f"  - {items[i].get('title') or ''} ({items[i].get('url') or 'без URL'})"
            for i in topic["item_indexes"]
        ]
        logger.info("Тема %s: %s\n%s", n, topic["topic"], "\n".join(lines))


def _item_urls(items: Sequence[Dict[str, Any]]) -> List[str]:
    urls: List[str] = []
    seen = set()
    for item in items:
        url = str(item.get("url") or "").strip()
        if url and url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def _raw_excerpt(raw: Optional[str]) -> str:
    """Сырой ответ для лога: целиком, если короткий, иначе начало … конец."""
    text = raw or ""
    if not text:
        return "(пусто)"
    edge = RAW_LOG_EDGE_CHARS
    if len(text) <= edge * 2:
        return repr(text)
    return f"{text[:edge]!r} … {text[-edge:]!r}"


def _try_json_object(text: str) -> Optional[Dict[str, Any]]:
    # strict=False: сырые переводы строк и табы внутри строк JSON не ломают разбор.
    try:
        data = json.loads(text, strict=False)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _strip_outer_fence(text: str) -> Optional[str]:
    """Снимает внешнее ```-ограждение, если им обёрнут весь ответ; иначе None."""
    if not (text.startswith("```") and text.endswith("```") and len(text) >= 6):
        return None
    inner = text[3:-3]
    # Первая строка ограждения — метка языка (```json); содержимое — со следующей строки.
    newline = inner.find("\n")
    if newline >= 0 and not inner[:newline].strip().startswith("{"):
        inner = inner[newline + 1 :]
    elif inner.lower().startswith("json"):
        inner = inner[4:]
    return inner.strip()


def _load_json_object(raw: str) -> Optional[Dict[str, Any]]:
    """JSON-объект из ответа модели.

    Порядок: весь текст как есть; весь ответ во внешнем ```-ограждении — без него;
    вырезка от первой { до последней }. Других кандидатов нет: блок кода внутри
    невалидного объекта (JSON-пример в body) за ответ не принимается.
    Блоки кода ``` внутри строк JSON (например, в body статьи) разбору не мешают.
    """
    text = (raw or "").strip()
    if not text:
        return None
    candidates: List[str] = [text]
    inner = _strip_outer_fence(text)
    if inner is not None:
        candidates.append(inner)
    for base in (inner, text):
        if base is None:
            continue
        start = base.find("{")
        end = base.rfind("}")
        if 0 <= start < end:
            candidates.append(base[start : end + 1])
    seen = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        data = _try_json_object(candidate)
        if data is not None:
            return data
    return None


def _load_plan_object(raw: str) -> Optional[Dict[str, Any]]:
    """Объект плана: JSON-объект с ключом topics-списком (пустой список допустим)."""
    data = _load_json_object(raw)
    if data is None or not isinstance(data.get("topics"), list):
        return None
    return data


def _parse_plan_payload(
    raw: str,
    item_count: int,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Темы с номерами материалов (в ответе с 1, в результате индексы с 0).

    Материал попадает не более чем в одну тему; тема без валидных материалов отбрасывается.
    """
    data = _load_plan_object(raw)
    if data is None:
        logger.error("Не удалось разобрать план статей DeepSeek как JSON")
        return [], []

    used: set = set()
    topics: List[Dict[str, Any]] = []
    for t in data["topics"]:
        if not isinstance(t, dict):
            continue
        topic = str(t.get("topic") or "").strip()
        if not topic:
            continue
        ids = t.get("item_ids")
        if not isinstance(ids, (list, tuple)):
            ids = [ids]
        indexes: List[int] = []
        for raw_id in ids:
            try:
                idx = int(raw_id) - 1
            except (TypeError, ValueError):
                continue
            if 0 <= idx < item_count and idx not in used and idx not in indexes:
                indexes.append(idx)
        if not indexes:
            continue
        used.update(indexes)
        topics.append(
            {
                "topic": topic,
                "angle": str(t.get("angle") or "").strip() or topic,
                "why_together": str(t.get("why_together") or "").strip(),
                "item_indexes": indexes,
                "search_queries": _parse_search_queries(t.get("search_queries")),
            }
        )

    keywords = []
    for kw in data.get("keywords") or []:
        phrase = str(kw).strip()
        if phrase:
            keywords.append(phrase)
    return topics, keywords


def _parse_search_queries(raw: Any) -> List[str]:
    """0–2 непустых поисковых запроса, каждый до 128 символов."""
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        return []
    queries: List[str] = []
    for q in raw:
        text = str(q or "").strip()[:SEARCH_QUERY_MAX_CHARS].strip()
        if text and text not in queries:
            queries.append(text)
        if len(queries) >= MAX_SEARCH_QUERIES:
            break
    return queries


def _parse_article_payload(raw: str) -> Optional[Dict[str, Any]]:
    data = _load_json_object(raw)
    if data is None:
        return None
    title = str(data.get("title") or "").strip()
    body = str(data.get("body") or "").strip()
    if not title or not body:
        return None
    return {
        "title": title,
        "body": body,
        "rationale": str(data.get("rationale") or "").strip(),
    }
