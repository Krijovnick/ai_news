import logging
import time
from collections import deque
from typing import Optional

import google.generativeai as genai  # type: ignore
import requests

from utils.config import Config


class ArticleSummarizer:
    """Класс для генерации кратких русскоязычных выжимок статей с помощью Gemini."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.provider = Config.SUMMARIZER_PROVIDER

        # Gemini настройки
        self.api_key = Config.GEMINI_API_KEY
        self.model_name = Config.GEMINI_MODEL
        self.gemini_rpm = max(1, Config.GEMINI_REQUESTS_PER_MINUTE)

        # DeepSeek настройки
        self.deepseek_api_key = Config.DEEPSEEK_API_KEY
        self.deepseek_model = Config.DEEPSEEK_MODEL
        self.deepseek_rpm = max(1, Config.DEEPSEEK_REQUESTS_PER_MINUTE)

        # OpenRouter настройки (можно проксировать deepseek через model=deepseek/deepseek-chat)
        self.openrouter_api_key = Config.OPENROUTER_API_KEY
        self.openrouter_model = Config.OPENROUTER_MODEL
        self.openrouter_base_url = Config.OPENROUTER_BASE_URL.rstrip("/")
        self.openrouter_rpm = max(1, Config.OPENROUTER_REQUESTS_PER_MINUTE)

        # Текущий лимит в зависимости от провайдера
        if self.provider == "gemini":
            self.requests_per_minute = self.gemini_rpm
        elif self.provider == "deepseek":
            self.requests_per_minute = self.deepseek_rpm
        elif self.provider == "openrouter":
            self.requests_per_minute = self.openrouter_rpm
        else:
            self.requests_per_minute = 4
        # Храним таймстемпы последних запросов, чтобы не ловить 429
        self._request_times = deque()

        if self.provider == "gemini":
            if not self.api_key:
                raise ValueError(
                    "GEMINI_API_KEY не установлен в .env, невозможно генерировать выжимки статей."
                )
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel(self.model_name)
        elif self.provider == "deepseek":
            if not self.deepseek_api_key:
                raise ValueError(
                    "DEEPSEEK_API_KEY не установлен в .env, невозможно генерировать выжимки статей."
                )
            self.model = None  # Не нужен SDK, работаем через HTTP
        elif self.provider == "openrouter":
            if not self.openrouter_api_key:
                raise ValueError(
                    "OPENROUTER_API_KEY не установлен в .env, невозможно генерировать выжимки статей."
                )
            self.model = None
        else:
            raise ValueError("Неверный SUMMARIZER_PROVIDER. Используйте 'gemini' или 'deepseek'.")

    def _respect_rate_limit(self):
        """Простая реализация rate-limit в рамках 1 минуты."""
        now = time.time()
        window = 60

        # Убираем устаревшие записи
        while self._request_times and now - self._request_times[0] > window:
            self._request_times.popleft()

        if len(self._request_times) >= self.requests_per_minute:
            sleep_for = window - (now - self._request_times[0]) + 0.2
            self.logger.warning(
                f"Достигнут лимит {self.requests_per_minute} rpm для Gemini, ждем {sleep_for:.1f} c"
            )
            time.sleep(sleep_for)

        self._request_times.append(time.time())

    @staticmethod
    def _extract_retry_delay(error_text: str) -> Optional[float]:
        """Пытаемся достать из текста ошибки рекомендуемую задержку."""
        import re

        match = re.search(r"retry in ([0-9]+(?:\.[0-9]+)?)s", error_text.lower())
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                return None
        return None

    @staticmethod
    def _simple_fallback_summary(title: str, description: str, max_sentences: int) -> Optional[str]:
        """Фолбэк: берем описание или заголовок и обрезаем."""
        base_text = description or title
        if not base_text:
            return None

        # Грубое разделение на предложения
        sentences = base_text.replace("\n", " ").split(".")
        sentences = [s.strip() for s in sentences if s.strip()]
        limited = ". ".join(sentences[:max_sentences])

        return limited if limited else None

    def _generate_content(self, prompt: str) -> str:
        """Делает вызов к выбранному провайдеру и возвращает текст ответа."""
        self._respect_rate_limit()

        if self.provider == "gemini":
            response = self.model.generate_content(prompt)
            return (response.text or "").strip()

        if self.provider == "deepseek":
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.deepseek_api_key}",
            }
            payload = {
                "model": self.deepseek_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
            }
            resp = requests.post(
                "https://api.deepseek.com/v1/chat/completions",
                json=payload,
                timeout=30,
                headers=headers,
            )
            if resp.status_code != 200:
                raise Exception(f"DeepSeek API error {resp.status_code}: {resp.text}")

            data = resp.json()
            choices = data.get("choices") or []
            if not choices:
                raise Exception("DeepSeek API вернул пустой список choices")
            message = choices[0].get("message", {})
            return (message.get("content") or "").strip()

        if self.provider == "openrouter":
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.openrouter_api_key}",
                # Рекомендуется, но не обязательно: реферер/название клиента для OpenRouter
                "HTTP-Referer": "https://github.com/",  # подставьте свой домен при желании
                "X-Title": "AI News Aggregator",
            }
            payload = {
                "model": self.openrouter_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
            }
            url = f"{self.openrouter_base_url}/chat/completions"
            resp = requests.post(url, json=payload, timeout=30, headers=headers)
            if resp.status_code != 200:
                raise Exception(f"OpenRouter API error {resp.status_code}: {resp.text}")

            data = resp.json()
            choices = data.get("choices") or []
            if not choices:
                raise Exception("OpenRouter API вернул пустой список choices")
            message = choices[0].get("message", {})
            return (message.get("content") or "").strip()

        raise RuntimeError("Неизвестный провайдер суммаризации")

    def summarize_article(
        self,
        title: str,
        description: str = "",
        source: str = "",
        url: str = "",
        max_sentences: int = 10,
    ) -> Optional[str]:
        """
        Генерирует краткую выжимку статьи на русском языке.

        Требования:
        - русский язык;
        - не более max_sentences предложений;
        - плавный, связный текст без маркированных списков;
        - без собственного заголовка (заголовок добавляем в коде).
        """
        prompt = (
            "Ты — помощник, который делает краткие русскоязычные пересказы новостей про ИИ "
            "для Telegram-канала.\n\n"
            "Задача:\n"
            f"- Кратко пересказать содержание новости так, как если бы ты объяснял это подписчику канала.\n"
            "- Пиши ТОЛЬКО на русском языке.\n"
            f"- Не более {max_sentences} предложений.\n"
            "- Текст должен быть плавным и связным, одна мысль логично вытекает из другой.\n"
            "- Не используй списки, маркеры, нумерацию.\n"
            "- Не придумывай свой заголовок и не повторяй исходный заголовок целиком в отдельной строке — "
            "заголовок будет добавлен отдельно в коде.\n"
            "- Не добавляй ссылки и не упоминай, что это пересказ или summary.\n\n"
            "Дано:\n"
            f"Заголовок: {title}\n"
        )

        if description:
            prompt += f"Описание/аннотация: {description}\n"
        if source:
            prompt += f"Источник: {source}\n"
        if url:
            prompt += f"URL: {url}\n"

        prompt += (
            "\nСделай итоговый связный пересказ на русском языке по этим данным."
        )

        # Даем две попытки: основная + один ретрай, если пришел 429
        for attempt in range(2):
            try:
                text = self._generate_content(prompt)

                if not text:
                    self.logger.warning("Gemini вернул пустой ответ при суммаризации")
                    return self._simple_fallback_summary(title, description, max_sentences)

                return text

            except Exception as e:
                err_text = str(e)
                is_rate_limited = "429" in err_text or "quota" in err_text.lower() or "retry" in err_text.lower()

                if is_rate_limited and attempt == 0:
                    delay = self._extract_retry_delay(err_text) or max(60 / self.requests_per_minute, 15)
                    self.logger.warning(
                        f"Лимит {self.provider} достигнут, ждем {delay:.1f} c и пробуем снова..."
                    )
                    time.sleep(delay)
                    continue

                self.logger.error(f"Ошибка при генерации выжимки через {self.provider}: {err_text}")
                return self._simple_fallback_summary(title, description, max_sentences)

        return self._simple_fallback_summary(title, description, max_sentences)


