"""SQLite-хранилище прогонов, материалов, разборов, статей и ключевых слов."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple
from urllib.parse import urlparse

from utils.config import Config, SEED_KEYWORDS

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _serialize_source_urls(value: Any) -> str:
    urls: List[str] = []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            parsed = [value] if value.strip() else []
        value = parsed
    if isinstance(value, (list, tuple)):
        for item in value:
            url = str(item or "").strip()
            if url and url not in urls:
                urls.append(url)
    return json.dumps(urls, ensure_ascii=False)


def _parse_source_urls(raw: Any) -> List[str]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, list):
        return [str(u).strip() for u in raw if str(u or "").strip()]
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    return [str(u).strip() for u in data if str(u or "").strip()]


ARTICLE_TITLE_EMPTY_ERROR = "Заголовок не может быть пустым"
ARTICLE_BODY_EMPTY_ERROR = "Текст статьи не может быть пустым"
ARTICLE_URLS_NOT_LIST_ERROR = "Ссылки нужно передать списком"


def normalize_article_urls(value: Any) -> List[str]:
    """Ссылки статьи из правки: срез пробелов, без пустых и дублей, только http(s).

    Невалидная ссылка — ValueError с сообщением на русском.
    """
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        raise ValueError(ARTICLE_URLS_NOT_LIST_ERROR)
    urls: List[str] = []
    for item in value:
        if item is None:
            continue
        if not isinstance(item, str):
            raise ValueError(ARTICLE_URLS_NOT_LIST_ERROR)
        url = item.strip()
        if not url:
            continue
        parsed = urlparse(url)
        if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc or any(
            ch.isspace() for ch in url
        ):
            raise ValueError(
                f"Некорректная ссылка: {url}. Нужен адрес, начинающийся с http:// или https://"
            )
        if url not in urls:
            urls.append(url)
    return urls


def _clean_article_text(title: Any, body: Any) -> Tuple[str, str]:
    """Заголовок и текст статьи из веба: срез пробелов; пустые — ValueError."""
    clean_title = str(title or "").strip()
    clean_body = str(body or "").strip()
    if not clean_title:
        raise ValueError(ARTICLE_TITLE_EMPTY_ERROR)
    if not clean_body:
        raise ValueError(ARTICLE_BODY_EMPTY_ERROR)
    return clean_title, clean_body


def _article_row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    data = dict(row)
    data["source_urls"] = _parse_source_urls(data.get("source_urls"))
    return data


class NewsDatabase:
    def __init__(self, path: Optional[str] = None):
        self.path = path or Config.DB_PATH
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self.ensure_schema()
        # Уборка старых failed — по возможности: занятая база (database is locked)
        # или другая ошибка не мешает открыть базу, доудалим при следующем открытии.
        try:
            self.delete_failed_runs()
        except Exception as exc:
            logger.warning("Не удалось удалить упавшие прогоны при открытии базы: %s", exc)
        self.seed_keywords_if_empty()

    def close(self) -> None:
        self._conn.close()

    def ensure_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                status TEXT NOT NULL,
                lookback_days INTEGER NOT NULL,
                error_text TEXT,
                telegram_sent INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                source TEXT,
                title TEXT,
                url TEXT,
                text TEXT,
                published_at TEXT,
                score REAL,
                extra_json TEXT,
                FOREIGN KEY(run_id) REFERENCES runs(id)
            );

            CREATE TABLE IF NOT EXISTS summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL UNIQUE,
                body TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES runs(id)
            );

            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                rationale TEXT,
                source_urls TEXT,
                FOREIGN KEY(run_id) REFERENCES runs(id)
            );

            CREATE TABLE IF NOT EXISTS keywords (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phrase TEXT NOT NULL,
                status TEXT NOT NULL,
                run_id INTEGER,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES runs(id)
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_keywords_phrase_ci
                ON keywords(phrase COLLATE NOCASE);
            """
        )
        self._ensure_articles_source_urls_column()
        self._conn.commit()

    def _ensure_articles_source_urls_column(self) -> None:
        cols = {
            row[1]
            for row in self._conn.execute("PRAGMA table_info(articles)").fetchall()
        }
        if "source_urls" not in cols:
            self._conn.execute("ALTER TABLE articles ADD COLUMN source_urls TEXT")

    def seed_keywords_if_empty(self) -> None:
        row = self._conn.execute(
            "SELECT COUNT(*) AS c FROM keywords WHERE status = 'active'"
        ).fetchone()
        if row and row["c"] > 0:
            return
        now = _utc_now_iso()
        for phrase in SEED_KEYWORDS:
            try:
                self._conn.execute(
                    "INSERT INTO keywords (phrase, status, run_id, updated_at) VALUES (?, 'active', NULL, ?)",
                    (phrase, now),
                )
            except sqlite3.IntegrityError:
                continue
        self._conn.commit()

    # --- keywords ---

    def get_keywords(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        if status:
            rows = self._conn.execute(
                "SELECT * FROM keywords WHERE status = ? ORDER BY phrase COLLATE NOCASE",
                (status,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM keywords ORDER BY status, phrase COLLATE NOCASE"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_active_keywords(self) -> List[str]:
        return [r["phrase"] for r in self.get_keywords("active")]

    def known_phrases_lower(self, statuses: Sequence[str]) -> Set[str]:
        placeholders = ",".join("?" for _ in statuses)
        rows = self._conn.execute(
            f"SELECT phrase FROM keywords WHERE status IN ({placeholders})",
            tuple(statuses),
        ).fetchall()
        return {r["phrase"].lower() for r in rows}

    def add_keyword(self, phrase: str, status: str = "active", run_id: Optional[int] = None) -> Optional[int]:
        phrase = (phrase or "").strip()
        if not phrase:
            return None
        now = _utc_now_iso()
        try:
            cur = self._conn.execute(
                "INSERT INTO keywords (phrase, status, run_id, updated_at) VALUES (?, ?, ?, ?)",
                (phrase, status, run_id, now),
            )
            self._conn.commit()
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None

    def update_keyword_phrase(self, keyword_id: int, phrase: str) -> bool:
        phrase = (phrase or "").strip()
        if not phrase:
            return False
        try:
            self._conn.execute(
                "UPDATE keywords SET phrase = ?, updated_at = ? WHERE id = ?",
                (phrase, _utc_now_iso(), keyword_id),
            )
            self._conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def set_keyword_status(self, keyword_id: int, status: str) -> None:
        self._conn.execute(
            "UPDATE keywords SET status = ?, updated_at = ? WHERE id = ?",
            (status, _utc_now_iso(), keyword_id),
        )
        self._conn.commit()

    def delete_keyword(self, keyword_id: int) -> None:
        self._conn.execute("DELETE FROM keywords WHERE id = ?", (keyword_id,))
        self._conn.commit()

    def propose_keywords(self, phrases: Sequence[str], run_id: int) -> int:
        """Сохраняет новые формулировки как proposed; active и rejected пропускает."""
        blocked = self.known_phrases_lower(("active", "rejected", "proposed"))
        added = 0
        now = _utc_now_iso()
        for raw in phrases:
            phrase = (raw or "").strip()
            if not phrase or phrase.lower() in blocked:
                continue
            try:
                self._conn.execute(
                    "INSERT INTO keywords (phrase, status, run_id, updated_at) VALUES (?, 'proposed', ?, ?)",
                    (phrase, run_id, now),
                )
                blocked.add(phrase.lower())
                added += 1
            except sqlite3.IntegrityError:
                continue
        self._conn.commit()
        return added

    # --- runs / content ---

    def create_run(self, lookback_days: int) -> int:
        cur = self._conn.execute(
            "INSERT INTO runs (started_at, status, lookback_days, error_text, telegram_sent) "
            "VALUES (?, 'running', ?, '', 0)",
            (_utc_now_iso(), lookback_days),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def delete_runs_without_items(self) -> List[int]:
        """Удаляет прогоны без единой строки в items тем же каскадом, что delete_run."""
        rows = self._conn.execute(
            """
            SELECT r.id FROM runs r
            WHERE NOT EXISTS (SELECT 1 FROM items i WHERE i.run_id = r.id)
            """
        ).fetchall()
        ids = [int(r["id"]) for r in rows]
        for run_id in ids:
            self.delete_run(run_id)
        return ids

    def delete_run(self, run_id: int) -> bool:
        """Удаляет прогон и всё, что к нему привязано.

        items, summaries, articles удаляются; proposed-ключи этого прогона удаляются;
        у active/rejected обнуляется run_id. False — прогона не было.
        """
        try:
            self._conn.execute("DELETE FROM items WHERE run_id = ?", (run_id,))
            self._conn.execute("DELETE FROM articles WHERE run_id = ?", (run_id,))
            self._conn.execute("DELETE FROM summaries WHERE run_id = ?", (run_id,))
            self._conn.execute(
                "DELETE FROM keywords WHERE run_id = ? AND status = 'proposed'", (run_id,)
            )
            self._conn.execute(
                "UPDATE keywords SET run_id = NULL WHERE run_id = ?", (run_id,)
            )
            cur = self._conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))
            deleted = cur.rowcount > 0
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        return deleted

    def delete_failed_runs(self) -> List[int]:
        """Удаляет старые прогоны со status=failed каскадом. running не трогает."""
        rows = self._conn.execute(
            "SELECT id FROM runs WHERE status = 'failed'"
        ).fetchall()
        ids = [int(r["id"]) for r in rows]
        for run_id in ids:
            self.delete_run(run_id)
        return ids

    def finish_run(
        self,
        run_id: int,
        *,
        status: str,
        error_text: str = "",
        telegram_sent: Optional[bool] = None,
    ) -> None:
        fields = ["finished_at = ?", "status = ?", "error_text = ?"]
        values: List[Any] = [_utc_now_iso(), status, error_text or ""]
        if telegram_sent is not None:
            fields.append("telegram_sent = ?")
            values.append(1 if telegram_sent else 0)
        values.append(run_id)
        self._conn.execute(
            f"UPDATE runs SET {', '.join(fields)} WHERE id = ?",
            values,
        )
        self._conn.commit()

    def mark_telegram_sent(self, run_id: int) -> None:
        self._conn.execute(
            "UPDATE runs SET telegram_sent = 1 WHERE id = ?",
            (run_id,),
        )
        self._conn.commit()

    def save_items(self, run_id: int, items: Sequence[Dict[str, Any]]) -> None:
        for item in items:
            published = item.get("published_date") or item.get("published_at")
            if isinstance(published, datetime):
                published_at = published.isoformat()
            else:
                published_at = str(published) if published else None
            extra = {
                k: v
                for k, v in item.items()
                if k
                not in {
                    "title",
                    "url",
                    "description",
                    "text",
                    "source",
                    "published_date",
                    "published_at",
                    "score",
                    "relevance_score",
                    "ranking_score",
                }
            }
            # JSON-safe: datetime etc.
            def _default(o):
                if isinstance(o, datetime):
                    return o.isoformat()
                return str(o)

            self._conn.execute(
                "INSERT INTO items (run_id, source, title, url, text, published_at, score, extra_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    item.get("source"),
                    item.get("title"),
                    item.get("url"),
                    item.get("description") or item.get("text") or "",
                    published_at,
                    item.get("ranking_score", item.get("score")),
                    json.dumps(extra, ensure_ascii=False, default=_default),
                ),
            )
        self._conn.commit()

    def save_summary(self, run_id: int, body: str) -> None:
        self._conn.execute(
            "INSERT INTO summaries (run_id, body) VALUES (?, ?) "
            "ON CONFLICT(run_id) DO UPDATE SET body = excluded.body",
            (run_id, body),
        )
        self._conn.commit()

    def save_articles(self, run_id: int, articles: Sequence[Dict[str, Any]]) -> None:
        for art in articles:
            self._conn.execute(
                "INSERT INTO articles (run_id, title, body, rationale, source_urls) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    run_id,
                    art.get("title") or "Без заголовка",
                    art.get("body") or "",
                    art.get("rationale") or "",
                    _serialize_source_urls(art.get("source_urls")),
                ),
            )
        self._conn.commit()

    def get_run(self, run_id: int) -> Optional[Dict[str, Any]]:
        """Прогон по id. failed не отдаётся — как будто прогона нет."""
        row = self._conn.execute(
            "SELECT * FROM runs WHERE id = ? AND status != 'failed'", (run_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_summary(self, run_id: int) -> Optional[str]:
        row = self._conn.execute(
            "SELECT body FROM summaries WHERE run_id = ?", (run_id,)
        ).fetchone()
        return row["body"] if row else None

    def get_articles_for_run(self, run_id: int) -> List[Dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM articles WHERE run_id = ? ORDER BY id", (run_id,)
        ).fetchall()
        return [_article_row_to_dict(r) for r in rows]

    def get_recent_article_titles(self, limit: int = 40) -> List[str]:
        """Заголовки последних статей — чтобы новый прогон не повторял темы."""
        rows = self._conn.execute(
            "SELECT title FROM articles ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [r["title"] for r in rows]

    def get_article(self, article_id: int) -> Optional[Dict[str, Any]]:
        row = self._conn.execute(
            "SELECT * FROM articles WHERE id = ?", (article_id,)
        ).fetchone()
        return _article_row_to_dict(row) if row else None

    def update_article(
        self,
        article_id: int,
        title: Any,
        body: Any,
        rationale: Any = None,
        source_urls: Any = None,
    ) -> Optional[Dict[str, Any]]:
        """Правка статьи из веба. None — статьи нет; ValueError — невалидные данные.

        rationale=None или source_urls=None оставляют прежнее значение поля.
        """
        current = self.get_article(article_id)
        if current is None:
            return None
        clean_title, clean_body = _clean_article_text(title, body)
        urls = (
            current["source_urls"] if source_urls is None else normalize_article_urls(source_urls)
        )
        if rationale is None:
            self._conn.execute(
                "UPDATE articles SET title = ?, body = ?, source_urls = ? WHERE id = ?",
                (clean_title, clean_body, json.dumps(urls, ensure_ascii=False), article_id),
            )
        else:
            self._conn.execute(
                "UPDATE articles SET title = ?, body = ?, rationale = ?, source_urls = ? "
                "WHERE id = ?",
                (
                    clean_title,
                    clean_body,
                    str(rationale).strip(),
                    json.dumps(urls, ensure_ascii=False),
                    article_id,
                ),
            )
        self._conn.commit()
        return self.get_article(article_id)

    def create_article(
        self,
        run_id: int,
        title: Any,
        body: Any,
        rationale: Any = None,
        source_urls: Any = None,
    ) -> Optional[Dict[str, Any]]:
        """Свой пост из веба в прогон. None — прогона нет; ValueError — невалидные данные.

        Валидация и нормализация ссылок те же, что в update_article.
        """
        if self.get_run(run_id) is None:
            return None
        clean_title, clean_body = _clean_article_text(title, body)
        urls = normalize_article_urls(source_urls)
        cur = self._conn.execute(
            "INSERT INTO articles (run_id, title, body, rationale, source_urls) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                run_id,
                clean_title,
                clean_body,
                str(rationale or "").strip(),
                json.dumps(urls, ensure_ascii=False),
            ),
        )
        self._conn.commit()
        return self.get_article(cur.lastrowid)

    def delete_article(self, article_id: int) -> bool:
        """Удаляет статью по id. False — статьи не было."""
        cur = self._conn.execute("DELETE FROM articles WHERE id = ?", (article_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def list_runs(self) -> List[Dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM runs WHERE status != 'failed' "
            "ORDER BY started_at DESC, id DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def group_runs_by_iso_week(runs: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Группирует прогоны по календарной ISO-неделе; новые недели сверху."""
    buckets: Dict[Tuple[int, int], Dict[str, Any]] = {}
    for run in runs:
        started = run.get("started_at") or ""
        try:
            dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
        except ValueError:
            dt = datetime.now(timezone.utc)
        iso = dt.isocalendar()
        key = (iso.year, iso.week)
        if key not in buckets:
            buckets[key] = {
                "year": iso.year,
                "week": iso.week,
                "label": f"{iso.year}-W{iso.week:02d}",
                "runs": [],
            }
        buckets[key]["runs"].append(run)

    weeks = list(buckets.values())
    weeks.sort(key=lambda w: (w["year"], w["week"]), reverse=True)
    for week in weeks:
        week["runs"].sort(key=lambda r: (r.get("started_at") or "", r.get("id") or 0), reverse=True)
    return weeks
