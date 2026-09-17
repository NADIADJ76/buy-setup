from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import invoices, pricing, sales, sheet

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


@app.get("/health")
def health():
    return {"status": "ok"}
