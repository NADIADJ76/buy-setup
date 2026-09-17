from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import storage
from ..customs import compute_cost_breakdown, get_rate_for_category, load_customs_rates, save_customs_rates
from ..models import CostInputs
from ..whatnot_strategy import compute_whatnot_strategy

router = APIRouter(tags=["pricing"])


@router.post("/pricing/breakdown")
def cost_breakdown(inputs: CostInputs):
    try:
        return compute_cost_breakdown(inputs)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/pricing/whatnot-strategy")
def whatnot_strategy(article_id: str, total_landed_cost_eur: float, safety_margin_rate: float = 0.15):
    return compute_whatnot_strategy(article_id, total_landed_cost_eur, safety_margin_rate)


@router.get("/pricing/customs-rates")
def get_customs_rates():
    return load_customs_rates()


@router.put("/pricing/customs-rates")
def update_customs_rates(rates: dict):
    save_customs_rates(rates)
    return rates


@router.get("/pricing/customs-rates/{category}")
def get_category_rate(category: str):
    return get_rate_for_category(category)
