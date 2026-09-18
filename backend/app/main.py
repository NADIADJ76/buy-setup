from __future__ import annotations
import logging
import traceback

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .routers import invoices, pricing, sales, sheet

logger = logging.getLogger("buy_setup")

app = FastAPI(
    title="Buy Setup API",
    description=(
        "Backend de l'appli Buy Setup refondue : import des factures Buyee, "
        "calcul du prix de revient (douane France + TVA), strategie d'enchere "
        "WhatNot, fiche produit telechargeable et suivi des ventes multi-plateformes."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # restreindre a l'URL du frontend en production
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(invoices.router)
app.include_router(pricing.router)
app.include_router(sales.router)
app.include_router(sheet.router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Catches any unexpected crash (e.g. a Buyee selector that no longer
    matches, a Scrapling/browser error) and turns it into a normal JSON
    error response. Without this, an unhandled exception can produce a raw
    500 that skips the CORS headers, which the browser then reports to the
    frontend as a generic "Failed to fetch" instead of a readable error."""
    logger.error("Unhandled exception on %s %s:\n%s", request.method, request.url.path, traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content={"detail": f"Erreur serveur : {exc.__class__.__name__}: {exc}"},
    )


@app.get("/health")
def health():
    return {"status": "ok"}
