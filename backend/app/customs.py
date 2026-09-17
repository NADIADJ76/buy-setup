"""French customs duty + VAT calculator for goods imported from Japan.

Rules implemented (indicative, based on French/EU customs rules as of 2026 --
always double check the exact HS code for a specific article on the official
simulator at https://www.douane.gouv.fr / RITA before relying on this for real
declarations):

- VAT (TVA) applies from the first euro on all commercial imports since the
  July 2021 EU e-commerce reform (no more de minimis exemption for VAT).
- Customs duty (droits de douane) is NOT charged when the intrinsic value of
  the shipment is <= 150 EUR. Above that threshold, duty = dutiable_base * rate.
- The dutiable base for both duty and VAT is: item price + shipping costs
  that are already known at the time of import (Japan domestic shipping +
  international shipping to France). This matches how customs values a
  shipment (item cost + freight + insurance).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .models import CostBreakdown, CostInputs

CUSTOMS_DUTY_FREE_THRESHOLD_EUR = 150.0
RATES_FILE = Path(__file__).parent / "config" / "customs_rates.json"


def load_customs_rates() -> dict:
    with open(RATES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    data.pop("_comment", None)
    return data


def save_customs_rates(rates: dict) -> None:
    with open(RATES_FILE, "w", encoding="utf-8") as f:
        json.dump(rates, f, ensure_ascii=False, indent=2)


def get_rate_for_category(category: str) -> dict:
    rates = load_customs_rates()
    return rates.get(category, rates["default"])


def compute_cost_breakdown(inputs: CostInputs) -> CostBreakdown:
    if inputs.jpy_to_eur_rate <= 0:
        raise ValueError("jpy_to_eur_rate must be > 0")

    item_price_eur = inputs.item_price_jpy * inputs.jpy_to_eur_rate
    japan_shipping_eur = inputs.japan_domestic_shipping_jpy * inputs.jpy_to_eur_rate
    intl_shipping_eur = inputs.international_shipping_eur

    rate_conf = get_rate_for_category(inputs.category)
    duty_rate = (
        inputs.customs_duty_rate_override
        if inputs.customs_duty_rate_override is not None
        else rate_conf["duty_rate"]
    )
    vat_rate = (
        inputs.vat_rate_override
        if inputs.vat_rate_override is not None
        else rate_conf["vat_rate"]
    )

    dutiable_base_eur = item_price_eur + japan_shipping_eur + intl_shipping_eur

    customs_duty_eur = 0.0
    if dutiable_base_eur > CUSTOMS_DUTY_FREE_THRESHOLD_EUR:
        customs_duty_eur = dutiable_base_eur * duty_rate

    # VAT is due on (goods + shipping + duty), no de minimis exemption.
    vat_eur = (dutiable_base_eur + customs_duty_eur) * vat_rate

    total_landed_cost_eur = dutiable_base_eur + customs_duty_eur + vat_eur

    return CostBreakdown(
        article_id=inputs.article_id,
        item_price_eur=round(item_price_eur, 2),
        japan_domestic_shipping_eur=round(japan_shipping_eur, 2),
        international_shipping_eur=round(intl_shipping_eur, 2),
        customs_duty_rate=duty_rate,
        vat_rate=vat_rate,
        dutiable_base_eur=round(dutiable_base_eur, 2),
        customs_duty_eur=round(customs_duty_eur, 2),
        vat_eur=round(vat_eur, 2),
        total_landed_cost_eur=round(total_landed_cost_eur, 2),
    )
