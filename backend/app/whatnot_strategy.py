"""Suggests a WhatNot live-auction starting price + escalation thresholds
based on the total landed cost of an article.

Logic:
- min_viable_price_eur = total_landed_cost * (1 + safety_margin_rate)
  This is the price under which you'd be selling at a loss once WhatNot's
  own selling fees are accounted for (see WHATNOT_FEE_RATE below).
- can_start_at_1_eur is True when the landed cost is low enough that even a
  final sale price roughly 3-4x the opening 1EUR bid (typical for lively
  penny auctions) would clear min_viable_price_eur. This is a heuristic,
  not a guarantee -- it flags "safe to try the excitement of a 1EUR open"
  vs "risky, start higher instead".
- x2_threshold / x3_threshold are prix de revient multiples: reference sale
  prices you should aim to reach so the sale is 2x / 3x your total cost.
"""
from __future__ import annotations

from .models import WhatnotStrategy

WHATNOT_FEE_RATE = 0.08  # approx. platform + payment processing fees, adjust as needed
DEFAULT_SAFETY_MARGIN_RATE = 0.15  # 15% margin on top of landed cost
ONE_EURO_OPEN_SAFE_MULTIPLIER = 4.0  # assume a 1EUR open typically climbs ~4x on a lively auction


def compute_whatnot_strategy(
    article_id: str,
    total_landed_cost_eur: float,
    safety_margin_rate: float = DEFAULT_SAFETY_MARGIN_RATE,
) -> WhatnotStrategy:
    min_viable_price_eur = total_landed_cost_eur * (1 + safety_margin_rate) / (1 - WHATNOT_FEE_RATE)

    can_start_at_1 = (1.0 * ONE_EURO_OPEN_SAFE_MULTIPLIER) >= min_viable_price_eur

    suggested_start_price_eur = 1.0 if can_start_at_1 else round(min_viable_price_eur / ONE_EURO_OPEN_SAFE_MULTIPLIER, 2)

    x2_threshold_eur = round(total_landed_cost_eur * 2, 2)
    x3_threshold_eur = round(total_landed_cost_eur * 3, 2)

    if can_start_at_1:
        notes = (
            f"Prix de revient bas ({total_landed_cost_eur:.2f} EUR) : tu peux lancer l'enchere a 1 EUR. "
            f"Vise au moins {min_viable_price_eur:.2f} EUR pour couvrir cout + marge + frais WhatNot (~{WHATNOT_FEE_RATE*100:.0f}%). "
            f"Objectif x2 : {x2_threshold_eur:.2f} EUR, objectif x3 : {x3_threshold_eur:.2f} EUR."
        )
    else:
        notes = (
            f"Prix de revient trop eleve ({total_landed_cost_eur:.2f} EUR) pour ouvrir a 1 EUR sans risque. "
            f"Prix de depart conseille : {suggested_start_price_eur:.2f} EUR. "
            f"Objectif x2 : {x2_threshold_eur:.2f} EUR, objectif x3 : {x3_threshold_eur:.2f} EUR."
        )

    return WhatnotStrategy(
        article_id=article_id,
        total_landed_cost_eur=round(total_landed_cost_eur, 2),
        safety_margin_rate=safety_margin_rate,
        min_viable_price_eur=round(min_viable_price_eur, 2),
        can_start_at_1_eur=can_start_at_1,
        suggested_start_price_eur=suggested_start_price_eur,
        x2_threshold_eur=x2_threshold_eur,
        x3_threshold_eur=x3_threshold_eur,
        notes=notes,
    )
