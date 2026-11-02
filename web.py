#!/usr/bin/env python3
"""Локальный веб-интерфейс: JSON API и собранный Vue из frontend/dist."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, jsonify, redirect, request, send_from_directory, url_for

from main import MANUAL_TITLE_LANGUAGE_ERROR, AINewsAggregator, normalize_manual_pairs
from utils.config import Config, setup_logging
from utils.db import NewsDatabase, group_runs_by_iso_week

MANUAL_PAIRS_ERROR = "Нужна хотя бы одна пара заголовка и текста"
ARTICLE_NOT_FOUND_ERROR = "Статья не найдена"
RUN_NOT_FOUND_ERROR = "Прогон не найден"
ARTICLE_PAYLOAD_ERROR = "Нужен JSON с полями title, body и source_urls"

DIST_DIR = Path(__file__).resolve().parent / "frontend" / "dist"
_DIST_MISSING = (
    "Нужна сборка фронтенда. В каталоге frontend выполните npm install и npm run build.",
    500,
    {"Content-Type": "text/plain; charset=utf-8"},
)

app = Flask(__name__, static_folder=None)
logger = setup_logging()


def get_db() -> NewsDatabase:
    return NewsDatabase()


def _keyword_phrase(db: NewsDatabase, kid: int) -> Optional[str]:
    for row in db.get_keywords():
        if row["id"] == kid:
            return row["phrase"]
    return None


def _is_fetch() -> bool:
    return request.headers.get("X-Requested-With") == "fetch"


def _spa_index():
    index_path = DIST_DIR / "index.html"
    if not index_path.is_file():
        return _DIST_MISSING
    return send_from_directory(DIST_DIR, "index.html")


@app.route("/assets/<path:filename>")
def frontend_assets(filename: str):
    assets_dir = DIST_DIR / "assets"
    if not assets_dir.is_dir():
        return _DIST_MISSING
    asset_path = assets_dir / filename
    if not asset_path.is_file():
        return "Не найдено", 404
    return send_from_directory(assets_dir, filename)


@app.route("/")
@app.route("/run/<int:run_id>")
@app.route("/article/<int:article_id>")
def spa_pages(run_id: Optional[int] = None, article_id: Optional[int] = None):
    return _spa_index()


@app.route("/api/weeks")
def api_weeks():
    db = get_db()
    runs = db.list_runs()
    weeks = group_runs_by_iso_week(runs)
    return jsonify({"weeks": weeks, "empty": not bool(runs)})


@app.route("/api/runs/<int:run_id>")
def api_run(run_id: int):
    db = get_db()
    run = db.get_run(run_id)
    if not run:
        return jsonify({"error": RUN_NOT_FOUND_ERROR}), 404
    summary = db.get_summary(run_id) or ""
    articles = db.get_articles_for_run(run_id)
    return jsonify({"run": run, "summary": summary, "articles": articles})


@app.route("/api/runs/<int:run_id>/articles", methods=["POST"])
def api_run_article_create(run_id: int):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "error": ARTICLE_PAYLOAD_ERROR}), 400
    db = get_db()
    try:
        article = db.create_article(
            run_id,
            title=payload.get("title"),
            body=payload.get("body"),
            rationale=payload.get("rationale"),
            source_urls=payload.get("source_urls"),
        )
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    if article is None:
        return jsonify({"ok": False, "error": RUN_NOT_FOUND_ERROR}), 404
    return jsonify({"ok": True, "article": article}), 201


@app.route("/api/articles/<int:article_id>")
def api_article(article_id: int):
    db = get_db()
    article = db.get_article(article_id)
    if not article:
        return jsonify({"error": ARTICLE_NOT_FOUND_ERROR}), 404
    return jsonify({"article": article})


@app.route("/api/articles/<int:article_id>", methods=["PUT", "PATCH"])
def api_article_update(article_id: int):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "error": ARTICLE_PAYLOAD_ERROR}), 400
    db = get_db()
    try:
        article = db.update_article(
            article_id,
            title=payload.get("title"),
            body=payload.get("body"),
            rationale=payload.get("rationale"),
            source_urls=payload.get("source_urls"),
        )
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    if article is None:
        return jsonify({"ok": False, "error": ARTICLE_NOT_FOUND_ERROR}), 404
    return jsonify({"ok": True, "article": article}), 200


@app.route("/api/articles/<int:article_id>", methods=["DELETE"])
def api_article_delete(article_id: int):
    db = get_db()
    if not db.delete_article(article_id):
        return jsonify({"ok": False, "error": ARTICLE_NOT_FOUND_ERROR}), 404
    return jsonify({"ok": True}), 200


@app.route("/api/keywords")
def api_keywords():
    db = get_db()
    return jsonify(
        {
            "active": db.get_keywords("active"),
            "proposed": db.get_keywords("proposed"),
            "rejected": db.get_keywords("rejected"),
        }
    )


@app.route("/keywords", methods=["GET", "POST"])
def keywords_page():
    if request.method == "GET":
        return _spa_index()

    db = get_db()
    error = None
    ok_payload: Dict[str, Any] = {"ok": True}

    action = request.form.get("action")
    try:
        if action == "add_active":
            phrase = (request.form.get("phrase") or "").strip()
            if not phrase:
                error = "Пустая фраза"
            else:
                kid = db.add_keyword(phrase, "active")
                if kid is None:
                    error = "Такая фраза уже есть"
                else:
                    ok_payload.update({"id": kid, "phrase": phrase})
        elif action == "edit":
            kid = int(request.form.get("id"))
            phrase = (request.form.get("phrase") or "").strip()
            if not db.update_keyword_phrase(kid, phrase):
                error = "Не удалось сохранить фразу (возможно, дубликат)"
            else:
                ok_payload.update({"id": kid, "phrase": phrase})
        elif action == "delete":
            db.delete_keyword(int(request.form.get("id")))
        elif action == "accept":
            kid = int(request.form.get("id"))
            phrase = _keyword_phrase(db, kid) or ""
            db.set_keyword_status(kid, "active")
            ok_payload.update({"id": kid, "phrase": phrase})
        elif action == "reject":
            kid = int(request.form.get("id"))
            phrase = _keyword_phrase(db, kid) or ""
            db.set_keyword_status(kid, "rejected")
            ok_payload.update({"id": kid, "phrase": phrase})
        elif action == "edit_proposed":
            kid = int(request.form.get("id"))
            phrase = (request.form.get("phrase") or "").strip()
            if not db.update_keyword_phrase(kid, phrase):
                error = "Не удалось поправить предложенную фразу"
            else:
                ok_payload.update({"id": kid, "phrase": phrase})
    except Exception as e:
        error = str(e)

    if _is_fetch():
        if error:
            return jsonify({"ok": False, "error": error}), 400
        return jsonify(ok_payload), 200

    if not error:
        return redirect(url_for("keywords_page"))

    return error, 400, {"Content-Type": "text/plain; charset=utf-8"}


@app.route("/api/manual-run", methods=["POST"])
def api_manual_run():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "error": MANUAL_PAIRS_ERROR}), 400
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        return jsonify({"ok": False, "error": MANUAL_PAIRS_ERROR}), 400

    prepared = normalize_manual_pairs(raw_items)
    if not prepared:
        return jsonify({"ok": False, "error": MANUAL_PAIRS_ERROR}), 400

    aggregator = AINewsAggregator(db=get_db())
    try:
        run_id = aggregator.run_manual(prepared)
    except ValueError as e:
        message = str(e) or MANUAL_TITLE_LANGUAGE_ERROR
        return jsonify({"ok": False, "error": message}), 400
    except Exception as e:
        logger.error("Ручной прогон: %s", e)
        return jsonify({"ok": False, "error": str(e)}), 500
    return jsonify({"ok": True, "run_id": run_id}), 200


def main():
    host = Config.WEB_HOST
    port = Config.WEB_PORT
    # Схема и стартовые слова создаются при первом обращении к NewsDatabase
    get_db()
    print(f"Веб-интерфейс: http://{host}:{port}")
    try:
        app.run(host=host, port=port, debug=False)
    except KeyboardInterrupt:
        print("Веб-интерфейс остановлен.")
        raise SystemExit(0)


if __name__ == "__main__":
    main()
