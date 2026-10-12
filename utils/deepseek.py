"""Клиент DeepSeek Chat Completions API."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

import requests

from utils.config import Config

logger = logging.getLogger(__name__)

API_URL = "https://api.deepseek.com/v1/chat/completions"
CHUNK_SIZE = 25


def load_author_prompt(path: Optional[str] = None) -> str:
    path = path or Config.AUTHOR_PROMPT_PATH
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        logger.warning("Файл промпта автора не найден: %s", path)
        return (
            "Ты женщина с большим опытом в ИИ и разработке. Пиши от первого лица "
            "на русском, как устная речь перед аудиторией. Названия продуктов оставляй "
            "в оригинале. Без английских вставок вроде «это game changer»."
        )


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

        if len(chunks) == 1:
            prompt = (
                "По материалам ниже напиши подробный разбор недели на русском: "
                "о чём пишут, какие технологии появились, чем помогают, где применять. "
                "Только текст разбора, без JSON.\n\n"
                + format_items_for_prompt(chunks[0])
            )
            return self._chat(
                [
                    {
                        "role": "system",
                        "content": "Ты аналитик ИИ-новостей. Пиши подробно и по делу на русском.",
                    },
                    {"role": "user", "content": prompt},
                ]
            )

        partials = []
        for idx, chunk in enumerate(chunks, 1):
            prompt = (
                f"Это часть {idx} из {len(chunks)} материалов недели. "
                "Кратко, но содержательно выдели темы, технологии и применения. На русском.\n\n"
                + format_items_for_prompt(chunk)
            )
            partials.append(
                self._chat(
                    [
                        {
                            "role": "system",
                            "content": "Ты аналитик ИИ-новостей. Пиши на русском.",
                        },
                        {"role": "user", "content": prompt},
                    ]
                )
            )

        merge_prompt = (
            "Собери из черновиков один цельный подробный разбор недели на русском: "
            "о чём пишут, какие технологии появились, чем помогают, где применять. "
            "Без дублирования и без JSON.\n\n"
            + "\n\n---\n\n".join(partials)
        )
        return self._chat(
            [
                {
                    "role": "system",
                    "content": "Ты аналитик ИИ-новостей. Пиши подробно на русском.",
                },
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
        author = author_prompt if author_prompt is not None else load_author_prompt()
        materials = format_items_for_prompt(items)
        allowed_urls = _item_urls(items)

        user_prompt = (
            f"{author}\n\n"
            f"Лимит статей: до {n}. Если полезных тем меньше — меньше; ноль допустим.\n"
            "Верни строго JSON-объект:\n"
            '{"articles":[{"title":"...","body":"...","rationale":"...",'
            '"source_urls":["https://..."]}],'
            '"keywords":["фраза1","фраза2"]}\n'
            "У каждой статьи source_urls — список URL из поля URL материалов выше, "
            "на которых основан текст статьи. Бери только URL из материалов; "
            "если опиралась на материал без URL — оставь source_urls пустым массивом.\n"
            "keywords — новые технологии и формулировки из материалов, которых ещё нет "
            "в известных списках; короткие фразы для поиска.\n\n"
            f"Разбор недели:\n{summary}\n\nМатериалы:\n{materials}"
        )

        raw = self._chat(
            [
                {
                    "role": "system",
                    "content": (
                        "Отвечай только валидным JSON без markdown-ограждений. "
                        "Статьи — на русском, голос автора из инструкции пользователя."
                    ),
                },
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
