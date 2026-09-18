"""Buyee.jp invoice/order scraper built on Scrapling.

IMPORTANT - read before using in production:
-----------------------------------------------
This module was written WITHOUT access to a live, logged-in Buyee account
(Claude cannot log into your personal account). The overall flow -- open
login page, submit credentials, then walk the order/invoice pages -- is
correct for how Buyee works, but the exact CSS selectors below
(LOGIN_SELECTORS / ORDER_LIST_SELECTORS / INVOICE_SELECTORS) are
best-effort placeholders based on Buyee's typical page structure and WILL
likely need small adjustments once you run this against your real account.

How to fix a selector that doesn't match:
1. Log into buyee.jp yourself in a normal browser.
2. Open devtools (F12) on the order history / invoice page.
3. Right click the element you need (price, photo, shipping line) ->
   "Inspect" -> right click the highlighted HTML -> "Copy selector".
4. Paste that selector into the matching entry below.

Credentials handling:
- BuyeeCredentials is only ever passed as a function argument, in memory.
- It is never written to a file, a log line, or the JSON storage layer.
- The Playwright/Scrapling session that holds the logged-in cookies is
  discarded at the end of `fetch_invoices()`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from .models import Article, BuyeeCredentials
from .storage import new_id

logger = logging.getLogger("buyee_scraper")

BUYEE_LOGIN_URL = "https://buyee.jp/signup/login"
BUYEE_ORDER_HISTORY_URL = "https://buyee.jp/order/mypage/order/list"

# --- Selectors: adjust these against your real, logged-in account -------
LOGIN_SELECTORS = {
    "username_field": "input[name='login_id']",
    "password_field": "input[name='password']",
    "submit_button": "button[type='submit']",
}

ORDER_LIST_SELECTORS = {
    "order_row": ".order-list__item, .mypage-order-list tr",
    "order_link": "a::attr(href)",
}

INVOICE_SELECTORS = {
    "article_row": ".order-detail__item, .item-detail-row",
    "article_name": ".item-name, .product-name::text",
    "article_photo": "img::attr(src)",
    "article_price": ".item-price, .price::text",
    "japan_shipping": ".domestic-shipping, .shipping-fee::text",
}


@dataclass
class ScrapeResult:
    articles: list[Article]
    warnings: list[str]


def _parse_price_text(text: str | None) -> float:
    """Turn a Buyee price string like '¥1,980' or '1,980円' into a float."""
    if not text:
        return 0.0
    digits = "".join(ch for ch in text if ch.isdigit() or ch == ".")
    try:
        return float(digits) if digits else 0.0
    except ValueError:
        return 0.0


def fetch_invoices(credentials: BuyeeCredentials, max_orders: int = 20) -> ScrapeResult:
    """Log into Buyee and pull recent orders/invoices: article name, photo,
    item price and Japan domestic shipping for each line item.

    Uses Scrapling's DynamicSession (a real, scriptable browser) because
    Buyee's login form and order pages are JS-rendered.
    """
    warnings: list[str] = []
    articles: list[Article] = []

    try:
        from scrapling.fetchers import DynamicSession
    except ImportError as exc:  # pragma: no cover - dependency install issue
        raise RuntimeError(
            "Scrapling n'est pas installe correctement. Lance : "
            "pip install \"scrapling[fetchers]\" && scrapling install"
        ) from exc

    def _do_login(page):
        """Runs inside Scrapling's browser via page_action: receives the real
        Playwright Page object to fill and submit the login form."""
        page.fill(LOGIN_SELECTORS["username_field"], credentials.username)
        page.fill(LOGIN_SELECTORS["password_field"], credentials.password)
        page.click(LOGIN_SELECTORS["submit_button"])
        page.wait_for_load_state("networkidle")

    with DynamicSession(headless=True, network_idle=True) as session:
        # page_action runs our login callback against the real browser page
        # right after navigation, before Scrapling hands back the parsed result.
        session.fetch(BUYEE_LOGIN_URL, page_action=_do_login)

        order_list_page = session.fetch(BUYEE_ORDER_HISTORY_URL)
        order_rows = order_list_page.css(ORDER_LIST_SELECTORS["order_row"])

        if not order_rows:
            warnings.append(
                "Aucune commande trouvee avec le selecteur actuel -- verifie "
                "ORDER_LIST_SELECTORS dans buyee_scraper.py contre ton compte reel."
            )

        order_links = []
        for row in order_rows[:max_orders]:
            hrefs = row.css(ORDER_LIST_SELECTORS["order_link"])
            if hrefs:
                order_links.append(hrefs[0])

        for link in order_links:
            invoice_url = link if link.startswith("http") else f"https://buyee.jp{link}"
            invoice_page = session.fetch(invoice_url)
            item_rows = invoice_page.css(INVOICE_SELECTORS["article_row"])

            for row in item_rows:
                name_el = row.css(INVOICE_SELECTORS["article_name"])
                photo_el = row.css(INVOICE_SELECTORS["article_photo"])
                price_el = row.css(INVOICE_SELECTORS["article_price"])
                shipping_el = row.css(INVOICE_SELECTORS["japan_shipping"])

                name = name_el.get() if name_el else "Article sans nom"
                photo_url = photo_el.get() if photo_el else None
                price_jpy = _parse_price_text(price_el.get() if price_el else None)
                shipping_jpy = _parse_price_text(shipping_el.get() if shipping_el else None)

                articles.append(
                    Article(
                        id=new_id(),
                        source_invoice_id=invoice_url,
                        name=name.strip() if isinstance(name, str) else "Article sans nom",
                        photo_url=photo_url,
                        item_price_jpy=price_jpy,
                        japan_domestic_shipping_jpy=shipping_jpy,
                    )
                )

    if not articles:
        warnings.append(
            "Aucun article extrait. Verifie les identifiants et les selecteurs "
            "dans buyee_scraper.py (voir le guide en haut du fichier)."
        )

    return ScrapeResult(articles=articles, warnings=warnings)


def fetch_invoices_demo() -> ScrapeResult:
    """Returns realistic-looking sample data so the rest of the app (cost
    calculator, WhatNot strategy, product sheet, sales tracking) can be
    built, tested and demoed without needing live Buyee credentials.
    Use the '/invoices/demo' endpoint to try the full flow end-to-end."""
    sample = [
        Article(
            id=new_id(),
            source_invoice_id="demo-invoice-1",
            name="Figurine Gundam RG 1/144 (occasion)",
            photo_url="https://picsum.photos/seed/gundam/400/400",
            item_price_jpy=4800,
            japan_domestic_shipping_jpy=600,
            category="toys_figures",
        ),
        Article(
            id=new_id(),
            source_invoice_id="demo-invoice-1",
            name="Coffret cartes One Piece OP-07 (scelle)",
            photo_url="https://picsum.photos/seed/onepiece/400/400",
            item_price_jpy=6200,
            japan_domestic_shipping_jpy=600,
            category="trading_cards",
        ),
    ]
    return ScrapeResult(articles=sample, warnings=[
        "Donnees de demonstration -- branche fetch_invoices() avec tes vrais identifiants "
        "pour remplacer ces exemples par tes factures reelles."
    ])
