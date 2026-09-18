from __future__ import annotations

import logging
import traceback

from fastapi import APIRouter, HTTPException

from .. import storage
from ..buyee_scraper import fetch_invoices, fetch_invoices_demo
from ..models import Article, BuyeeCredentials

logger = logging.getLogger("buy_setup")

router = APIRouter(prefix="/invoices", tags=["invoices"])


@router.post("/import")
def import_invoices(credentials: BuyeeCredentials):
    """Logs into Buyee with the given credentials (held only for this
    request), scrapes recent invoices, and stores the extracted articles.
    Credentials are discarded as soon as this request returns.

    Any crash here (a Buyee selector that no longer matches, a browser/
    network error, ...) is converted to a clean HTTPException instead of
    an unhandled exception. This matters beyond readability: an unhandled
    exception skips the CORS middleware, and the browser then reports the
    whole request to the frontend as a generic "Failed to fetch" instead
    of the real error message."""
    try:
        result = fetch_invoices(credentials)
    except Exception as exc:
        logger.error("Echec de l'import Buyee:\n%s", traceback.format_exc())
        raise HTTPException(
            status_code=502,
            detail=(
                "Impossible de recuperer les factures Buyee "
                f"({exc.__class__.__name__}: {exc}). Verifie tes identifiants, "
                "ou utilise 'Charger des donnees de demo' en attendant que le "
                "scraper soit ajuste (voir backend/app/buyee_scraper.py)."
            ),
        )

    saved = storage.upsert_articles([a.model_dump(mode="json") for a in result.articles])
    return {"articles": saved, "warnings": result.warnings}


@router.post("/demo")
def import_invoices_demo():
    """Loads sample articles so you can try the rest of the app (cost
    calculator, WhatNot strategy, product sheet, sales tracking) without
    needing real Buyee credentials yet."""
    result = fetch_invoices_demo()
    saved = storage.upsert_articles([a.model_dump(mode="json") for a in result.articles])
    return {"articles": saved, "warnings": result.warnings}


@router.get("")
def list_articles():
    return storage.list_articles()


@router.get("/{article_id}")
def get_article(article_id: str):
    article = storage.get_article(article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article introuvable")
    return article


@router.put("/{article_id}")
def update_article(article_id: str, article: Article):
    if article.id != article_id:
        raise HTTPException(status_code=400, detail="id mismatch")
    saved = storage.upsert_articles([article.model_dump(mode="json")])
    return next(a for a in saved if a["id"] == article_id)
