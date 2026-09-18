from __future__ import annotations

import logging
import traceback

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from .. import storage
from ..customs import compute_cost_breakdown
from ..models import Article, CostInputs
from ..product_sheet import generate_product_sheet_pdf
from ..whatnot_strategy import compute_whatnot_strategy

logger = logging.getLogger("buy_setup")

router = APIRouter(prefix="/sheet", tags=["sheet"])


@router.post("/{article_id}/generate")
def generate_sheet(article_id: str, inputs: CostInputs):
    article_dict = storage.get_article(article_id)
    if not article_dict:
        raise HTTPException(status_code=404, detail="Article introuvable")
    article = Article(**article_dict)

    try:
        cost = compute_cost_breakdown(inputs)
        strategy = compute_whatnot_strategy(article_id, cost.total_landed_cost_eur)
        pdf_path = generate_product_sheet_pdf(article, cost, strategy)
    except Exception as exc:
        logger.error("Echec de generation de la fiche PDF:\n%s", traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Erreur lors de la generation de la fiche : {exc}")

    return {"pdf_path": str(pdf_path), "download_url": f"/sheet/{article_id}/download"}


@router.get("/{article_id}/download")
def download_sheet(article_id: str):
    from pathlib import Path

    pdf_path = Path(__file__).parent.parent / "data" / "sheets" / f"fiche_{article_id}.pdf"
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="Fiche pas encore generee")
    return FileResponse(str(pdf_path), media_type="application/pdf", filename=pdf_path.name)
