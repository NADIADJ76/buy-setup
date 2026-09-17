from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import storage
from ..buyee_scraper import fetch_invoices, fetch_invoices_demo
from ..models import Article, BuyeeCredentials

router = APIRouter(prefix="/invoices", tags=["invoices"])


@router.post("/import")
def import_invoices(credentials: BuyeeCredentials):
    """Logs into Buyee with the given credentials (held only for this
    request), scrapes recent invoices, and stores the extracted articles.
    Credentials are discarded as soon as this request returns."""
    try:
        result = fetch_invoices(credentials)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

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
