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
        "system",
        "author",
        "user",
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

    def _chat(self, messages: List[Dict[str, str]], temperature: float = 0.7) -> str:
        response = requests.post(
            API_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
            },
            timeout=180,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()

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
        articles_per_run: Optional[int] = None,
        author_prompt: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        n = articles_per_run if articles_per_run is not None else Config.ARTICLES_PER_RUN
        prompts = load_prompts()["articles_and_keywords"]
        author = author_prompt if author_prompt is not None else prompts["author"]
        materials = format_items_for_prompt(items)
        allowed_urls = _item_urls(items)

        user_prompt = _fill(
            prompts["user"],
            author=author,
            n=n,
            summary=summary,
            materials=materials,
        )

        raw = self._chat(
            [
                {"role": "system", "content": prompts["system"]},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.8,
        )
        return _parse_articles_payload(raw, max_articles=n, allowed_urls=allowed_urls)


def _item_urls(items: Sequence[Dict[str, Any]]) -> List[str]:
    urls: List[str] = []
    seen = set()
    for item in items:
        url = str(item.get("url") or "").strip()
        if url and url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def _normalize_article_source_urls(
    raw: Any,
    allowed_urls: Optional[Sequence[str]] = None,
) -> List[str]:
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        return []
    allowed_set = (
        {u for u in allowed_urls if u} if allowed_urls is not None else None
    )
    result: List[str] = []
    for item in raw:
        url = str(item or "").strip()
        if not url or url in result:
            continue
        if allowed_set is not None and url not in allowed_set:
            continue
        result.append(url)
    return result


def _parse_articles_payload(
    raw: str,
    max_articles: int,
    allowed_urls: Optional[Sequence[str]] = None,
) -> Tuple[List[Dict[str, Any]], List[str]]:
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
        if start >= 0 and end > start:
            data = json.loads(text[start : end + 1])
        else:
            logger.error("Не удалось разобрать ответ DeepSeek как JSON")
            return [], []

    articles_raw = data.get("articles") or []
    keywords_raw = data.get("keywords") or []
    articles: List[Dict[str, Any]] = []
    for art in articles_raw[:max_articles]:
        if not isinstance(art, dict):
            continue
        title = str(art.get("title") or "").strip()
        body = str(art.get("body") or "").strip()
        if not title or not body:
            continue
        articles.append(
            {
                "title": title,
                "body": body,
                "rationale": str(art.get("rationale") or "").strip(),
                "source_urls": _normalize_article_source_urls(
                    art.get("source_urls"),
                    allowed_urls=allowed_urls,
                ),
            }
        )
    keywords = []
    for kw in keywords_raw:
        phrase = str(kw).strip()
        if phrase:
            keywords.append(phrase)
    return articles, keywords
