"""Very small JSON-file based persistence layer.

No database server required to run the app locally. Swap this out for a
real DB (Postgres/SQLite) later if the volume of articles grows -- the
router code only talks to the functions below, not to the file format.

Credentials are explicitly NEVER written here.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

ARTICLES_FILE = DATA_DIR / "articles.json"
SALES_FILE = DATA_DIR / "sales.json"


def _read(file: Path) -> list[dict[str, Any]]:
    if not file.exists():
        return []
    with open(file, "r", encoding="utf-8") as f:
        return json.load(f)


def _write(file: Path, items: list[dict[str, Any]]) -> None:
    with open(file, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2, default=str)


def new_id() -> str:
    return uuid.uuid4().hex[:12]


# --- Articles -----------------------------------------------------------

def list_articles() -> list[dict]:
    return _read(ARTICLES_FILE)


def upsert_articles(new_articles: list[dict]) -> list[dict]:
    existing = {a["id"]: a for a in _read(ARTICLES_FILE)}
    for art in new_articles:
        existing[art["id"]] = art
    merged = list(existing.values())
    _write(ARTICLES_FILE, merged)
    return merged


def get_article(article_id: str) -> dict | None:
    for a in _read(ARTICLES_FILE):
        if a["id"] == article_id:
            return a
    return None


def delete_article(article_id: str) -> bool:
    """Removes one article (e.g. a leftover 'Charger des donnees de demo'
    sample the user wants to clear out). Returns True if it existed."""
    existing = _read(ARTICLES_FILE)
    remaining = [a for a in existing if a["id"] != article_id]
    if len(remaining) == len(existing):
        return False
    _write(ARTICLES_FILE, remaining)
    return True


# --- Sales ----------------------------------------------------------------

def list_sales() -> list[dict]:
    return _read(SALES_FILE)


def upsert_sale(sale: dict) -> dict:
    sales = _read(SALES_FILE)
    for i, s in enumerate(sales):
        if s["id"] == sale["id"]:
            sales[i] = sale
            _write(SALES_FILE, sales)
            return sale
    sales.append(sale)
    _write(SALES_FILE, sales)
    return sale


def delete_sale(sale_id: str) -> None:
    sales = [s for s in _read(SALES_FILE) if s["id"] != sale_id]
    _write(SALES_FILE, sales)
