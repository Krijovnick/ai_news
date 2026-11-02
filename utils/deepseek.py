"""Клиент DeepSeek Chat Completions API."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

import requests
import yaml

from utils.config import Config

logger = logging.getLogger(__name__)

API_URL = "https://api.deepseek.com/v1/chat/completions"
CHUNK_SIZE = 25
# И плану, и статье даём максимум вывода deepseek-chat.
PLAN_MAX_TOKENS = 8192
ARTICLE_MAX_TOKENS = 8192

# Search/Fetch API DeepSeek: полные тексты и дополнительные источники для статьи.
FETCH_URL = "https://api.deepseek.com/v1/tools/fetch"
SEARCH_URL = "https://api.deepseek.com/v1/tools/search"
TOOLS_TIMEOUT = 60
SEARCH_MIN_RERANK = 1.5
SEARCH_QUERY_MAX_CHARS = 128
MAX_SEARCH_QUERIES = 2

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

    def _chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        response = requests.post(
            API_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=300,
        )
        response.raise_for_status()
        data = response.json()
        choice = data["choices"][0]
        if choice.get("finish_reason") == "length":
            logger.warning(
                "Ответ DeepSeek обрезан по max_tokens (%s)", max_tokens or "по умолчанию"
            )
        # content может прийти null — отдаём пустую строку, разбор решит дальше.
        return (choice["message"].get("content") or "").strip()

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
                ]
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
                    ]
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
            ]
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
        # Ошибка запроса плана пробрасывается: без плана статей нет.
        raw_plan = self._chat(
            [
                {"role": "system", "content": prompts["plan_system"]},
                {"role": "user", "content": plan_prompt},
            ],
            temperature=0.3,
            max_tokens=PLAN_MAX_TOKENS,
        )
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
            try:
                raw_article = self._chat(
                    [
                        {"role": "system", "content": prompts["write_system"]},
                        {"role": "user", "content": write_prompt},
                    ],
                    temperature=0.8,
                    max_tokens=ARTICLE_MAX_TOKENS,
                )
            # Сеть, HTTP-ошибка или битая структура ответа — пропускаем только эту статью.
            except (
                requests.RequestException,
                KeyError,
                IndexError,
                TypeError,
                AttributeError,
                ValueError,
            ) as exc:
                logger.error("Статья «%s» не написана: %s", topic["topic"], exc)
                continue
            article = _parse_article_payload(raw_article)
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
            logger.warning("Search DeepSeek: нет подходящих результатов для «%s»", query)
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
            materials.append(
                {
                    "title": item.get("title") or "",
                    "source": item.get("source") or "",
                    "url": url,
                    "text": rss_text[: Config.ARTICLE_ITEM_TEXT_CHARS],
                    "full_text": self._fetch_text(url) if (use_web and url) else "",
                }
            )
        extras: List[Dict[str, Any]] = []
        if use_web:
            seen = {m["url"] for m in materials if m["url"]}
            for query in search_queries:
                extras.extend(self._search(query, seen))
        return materials, extras


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


def _load_json_object(raw: str) -> Optional[Dict[str, Any]]:
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Попытка вырезать объект
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return data if isinstance(data, dict) else None


def _parse_plan_payload(
    raw: str,
    item_count: int,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Темы с номерами материалов (в ответе с 1, в результате индексы с 0).

    Материал попадает не более чем в одну тему; тема без валидных материалов отбрасывается.
    """
    data = _load_json_object(raw)
    if data is None:
        logger.error("Не удалось разобрать план статей DeepSeek как JSON")
        return [], []

    used: set = set()
    topics: List[Dict[str, Any]] = []
    for t in data.get("topics") or []:
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
