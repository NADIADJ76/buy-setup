"""Generates a downloadable, printable/postable product sheet (PDF) for one
article, ready to use as the basis of a WhatNot listing: photo, name,
price breakdown, and the suggested WhatNot auction strategy.
"""
from __future__ import annotations

import io
from pathlib import Path

import requests
from PIL import Image
from reportlab.lib.pagesizes import A5
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from .models import Article, CostBreakdown, WhatnotStrategy

SHEETS_DIR = Path(__file__).parent / "data" / "sheets"
SHEETS_DIR.mkdir(parents=True, exist_ok=True)


def _load_photo(article: Article) -> Image.Image | None:
    src = article.photo_local_path or article.photo_url
    if not src:
        return None
    try:
        if src.startswith("http"):
            resp = requests.get(src, timeout=10)
            resp.raise_for_status()
            return Image.open(io.BytesIO(resp.content)).convert("RGB")
        return Image.open(src).convert("RGB")
    except Exception:
        return None


def generate_product_sheet_pdf(
    article: Article,
    cost: CostBreakdown,
    strategy: WhatnotStrategy,
) -> Path:
    out_path = SHEETS_DIR / f"fiche_{article.id}.pdf"
    width, height = A5
    c = canvas.Canvas(str(out_path), pagesize=A5)

    margin = 10 * mm
    y = height - margin

    c.setFont("Helvetica-Bold", 14)
    c.drawString(margin, y, article.name[:60])
    y -= 10 * mm

    photo = _load_photo(article)
    photo_box = 60 * mm
    if photo:
        tmp_img_path = SHEETS_DIR / f"_tmp_{article.id}.jpg"
        photo.thumbnail((900, 900))
        photo.save(tmp_img_path, format="JPEG", quality=85)
        c.drawImage(
            str(tmp_img_path),
            margin,
            y - photo_box,
            width=photo_box,
            height=photo_box,
            preserveAspectRatio=True,
            anchor="n",
        )
        tmp_img_path.unlink(missing_ok=True)
    y -= photo_box + 6 * mm

    c.setFont("Helvetica", 10)
    lines = [
        f"Prix article (JPY->EUR) : {cost.item_price_eur:.2f} EUR",
        f"Livraison Japon (domestique) : {cost.japan_domestic_shipping_eur:.2f} EUR",
        f"Livraison internationale (Japon -> France) : {cost.international_shipping_eur:.2f} EUR",
        f"Droits de douane ({cost.customs_duty_rate*100:.1f}%) : {cost.customs_duty_eur:.2f} EUR",
        f"TVA ({cost.vat_rate*100:.1f}%) : {cost.vat_eur:.2f} EUR",
        "",
        f"PRIX DE REVIENT TOTAL : {cost.total_landed_cost_eur:.2f} EUR",
        "",
        f"Depart WhatNot conseille : {strategy.suggested_start_price_eur:.2f} EUR"
        + (" (1 EUR OK)" if strategy.can_start_at_1_eur else ""),
        f"Seuil x2 : {strategy.x2_threshold_eur:.2f} EUR",
        f"Seuil x3 : {strategy.x3_threshold_eur:.2f} EUR",
    ]
    for line in lines:
        c.drawString(margin, y, line)
        y -= 6 * mm

    if article.notes:
        y -= 4 * mm
        c.setFont("Helvetica-Oblique", 9)
        c.drawString(margin, y, f"Notes : {article.notes[:90]}")

    c.showPage()
    c.save()
    return out_path
