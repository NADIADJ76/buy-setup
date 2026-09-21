"""Buyee.jp invoice/order scraper built on Scrapling (browser automation +
session/login) with BeautifulSoup as a complement for HTML parsing.

Verified against a real, logged-in Buyee account on 2026-09-18
-----------------------------------------------------------------
Unlike the very first version of this file (which guessed at Buyee's page
structure), the selectors below were confirmed against two real pages the
user exported directly from their own account:

1. "Colis expedies" (https://buyee.jp/mybaggages/shipped/{page}) -- the list
   of packages Buyee has already shipped to France. Each package
   (`li.luggageInfo`) contains:
   - `table.luggageInfo_order`: one row per item/order in the package
     (marketplace, order number, item name + link, "Fiche complete" link).
   - `div.amount_info_container` (hidden in the DOM until the "Frais de
     port" toggle is clicked, but already present -- no click needed): a
     table of the Japan-domestic shipping fee per item (keyed by the same
     id that appears at the end of the item's own URL), followed by a
     `<dl>` with the package-level totals, including the REAL
     international (Japan -> France) shipping fee Buyee actually charged,
     sometimes together with Buyee's own EUR conversion of that total.
   - `div.delivery_info_container` (same hidden-until-toggled pattern): the
     shipping method (e.g. EMS) and the delivery address -- not currently
     used for cost calculation but kept in mind for future use.
2. "Fiche complete" (https://buyee.jp/myorders/.../details, one per
   item/order): a Knockout.js-rendered page with `div.itemCard__item`
   (photo + item name) and `div.g-priceDetails` (the price actually billed
   for that item, plus Buyee's own EUR conversion when the account has
   that feature enabled).

The login URL/selectors below are still best-effort (Claude cannot log into
your account to verify them), so `_login_looks_successful()` checks the
post-login page and reports a clear warning instead of silently scraping an
empty/login page if the credentials or the selectors are off.

How to fix a selector that stops matching (Buyee redesigns its site from
time to time):
1. Log into buyee.jp yourself in a normal browser.
2. Open devtools (F12) on the page in question.
3. Right click the element you need -> "Inspect" -> right click the
   highlighted HTML -> "Copy selector".
4. Paste that selector into the matching entry below.

Credentials handling:
- BuyeeCredentials is only ever passed as a function argument, in memory.
- It is never written to a file, a log line, or the JSON storage layer.
- The Playwright/Scrapling session that holds the logged-in cookies is
  discarded at the end of `fetch_invoices()`.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .models import Article, BuyeeCredentials
from .storage import new_id

logger = logging.getLogger("buyee_scraper")

BUYEE_BASE_URL = "https://buyee.jp"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class _SimpleResponse:
    """Minimal stand-in for a Scrapling browser Response, built from a
    plain requests.Response, so the same helpers below (_page_diagnostic,
    the packages loop) work whether a page came from the real browser
    (login) or from a lightweight HTTP GET (the Colis list -- see the
    memory-usage comment in fetch_invoices for why)."""

    def __init__(self, resp: requests.Response):
        self.html_content = resp.text
        self.url = resp.url


class _HttpSessionAdapter:
    """Wraps a plain requests.Session so it exposes the same .fetch(url)
    interface as a Scrapling browser session."""

    def __init__(self, http_session: requests.Session):
        self._session = http_session

    def fetch(self, url: str) -> _SimpleResponse:
        resp = self._session.get(url, timeout=25)
        return _SimpleResponse(resp)

# --- Login: CONFIRMED against a real, logged-out Buyee login page
# (https://buyee.jp/signup/login) on 2026-09-18. The form has id
# "login_form" and posts to /signup/login, but the "Login" button is NOT a
# <button>/<input type=submit> -- it's a plain <a id="login_submit"
# href="javascript:void(0);">, presumably wired up by JS to first fill a
# hidden "login[fingerprintData]" field (a browser-fingerprint anti-bot
# check) before actually submitting. Because that only runs client-side, we
# still click the real element (via Playwright, a real browser) rather than
# submitting the form ourselves, so that JS handler fires normally.
BUYEE_LOGIN_URL = f"{BUYEE_BASE_URL}/signup/login"
LOGIN_SELECTORS = {
    # Kept for backward compatibility / documentation; the actual login now
    # tries USERNAME_FIELD_CANDIDATES etc. below (confirmed selector first).
    "username_field": "input#login_mailAddress",
    "password_field": "input#login_password",
    "submit_button": "#login_submit",
}
USERNAME_FIELD_CANDIDATES = [
    "input#login_mailAddress",
    "input[name='login[mailAddress]']",
    "input[name='login_id']",
    "input[type='email']",
]
PASSWORD_FIELD_CANDIDATES = [
    "input#login_password",
    "input[name='login[password]']",
    "input[type='password']",
]
SUBMIT_BUTTON_CANDIDATES = [
    "#login_submit",
    "a#login_submit",
    "button[type='submit']",
    "input[type='submit']",
]
FIELD_TRY_TIMEOUT_MS = 4000

# --- 2FA / email verification: Buyee can flag a login from an unrecognised
# device or IP (confirmed on 2026-09-18: a real login attempt from this
# app's cloud server triggered a "connexion douteuse" email with a 6-digit
# code) and show a code-entry page instead of logging straight in. The
# exact selector for that page is a best-effort guess (not yet confirmed
# against real HTML, unlike the fields above) -- if it doesn't match,
# `login_debug` below will report the page title/URL so it can be fixed
# the same way the login fields were.
VERIFICATION_CODE_FIELD_CANDIDATES = [
    "input[name='certification_code']",
    "input#certification_code",
    "input[name='auth_code']",
    "input[name='verify_code']",
    "input[name='verification_code']",
    "input[name*='code']",
    "input[type='tel']",
    "input[type='number']",
]

# --- "Colis expedies" list: CONFIRMED against a real account. ------------
BUYEE_BAGGAGES_URL_TEMPLATE = BUYEE_BASE_URL + "/mybaggages/shipped/{page}"
MAX_BAGGAGE_PAGES = 5


@dataclass
class ScrapeResult:
    articles: list[Article] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _parse_jpy(text: str | None) -> float:
    """Turns a Buyee price string like '3,750 YENS' or '¥1,980' into a
    float."""
    if not text:
        return 0.0
    digits = "".join(ch for ch in text if ch.isdigit() or ch == ".")
    try:
        return float(digits) if digits else 0.0
    except ValueError:
        return 0.0


def _parse_eur_from_text(text: str | None) -> float | None:
    """Buyee sometimes shows its own EUR conversion next to a JPY amount,
    e.g. '(€105.49)' or '€183.99   (   31,450 YENS   )'. Pulls the euro
    figure out when present, returns None otherwise (most accounts don't
    have this currency-conversion feature turned on, which is fine -- the
    app still works from the JPY figures and a manually entered rate)."""
    if not text:
        return None
    m = re.search(r"€\s*([\d.,]+)", text)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def _item_id_from_href(href: str | None) -> str | None:
    """The 'Identifiant' column of the per-item shipping-fee table matches
    the last path segment of the item's own listing URL, whatever the
    marketplace it came from, e.g.:
      https://buyee.jp/item/jdirectitems/auction/q1235841865 -> 'q1235841865'
      https://buyee.jp/mercari/item/m39503153117              -> 'm39503153117'
    """
    if not href:
        return None
    return href.rstrip("/").split("/")[-1]


def _parse_package(pkg_soup: BeautifulSoup) -> tuple[list[dict], list[str]]:
    """Parses one <li class="luggageInfo"> package card (one 'colis') into
    a list of raw item dicts (one per order/article row) plus any
    warnings specific to this package."""
    warnings: list[str] = []
    items: list[dict] = []

    # --- 1. "Contenu du colis": one row per item/order in this package ---
    order_table = pkg_soup.find("table", class_="luggageInfo_order")
    order_rows = []
    if order_table and order_table.find("tbody"):
        order_rows = order_table.find("tbody").find_all("tr")[1:]  # skip header row
    if not order_rows:
        warnings.append(
            "Un colis Buyee n'a pas ete reconnu (table.luggageInfo_order "
            "introuvable ou vide) -- selecteurs peut-etre a ajuster."
        )

    for row in order_rows:
        cells = row.find_all("td")
        if len(cells) < 3:
            continue
        site_de_vente = cells[0].get_text(strip=True)
        order_number = cells[1].get_text(strip=True)
        name_link = cells[2].find("a")
        name = name_link.get_text(strip=True) if name_link else cells[2].get_text(strip=True)
        item_href = name_link["href"] if name_link and name_link.get("href") else None
        item_url = urljoin(BUYEE_BASE_URL, item_href) if item_href else None
        item_id = _item_id_from_href(item_href)

        fiche_link = row.find("a", class_="g-button")
        fiche_url = (
            urljoin(BUYEE_BASE_URL, fiche_link["href"])
            if fiche_link and fiche_link.get("href")
            else None
        )

        quantity = 1
        # The quantity column is the one right before the trailing
        # "Fiche complete" button column.
        for cell in reversed(cells[:-1]):
            txt = cell.get_text(strip=True)
            if txt.isdigit():
                quantity = int(txt)
                break

        items.append(
            {
                "site_de_vente": site_de_vente,
                "order_number": order_number,
                "name": name or "Article sans nom",
                "item_url": item_url,
                "item_id": item_id,
                "fiche_url": fiche_url,
                "quantity": quantity,
            }
        )

    # --- 2. "Frais de port": per-item JP domestic shipping + package-level
    # international shipping (already hidden-but-present in the DOM, no
    # click needed). -------------------------------------------------------
    jp_shipping_by_id: dict[str, float] = {}
    international_shipping_jpy = 0.0
    international_shipping_eur_buyee: float | None = None

    amount_container = pkg_soup.find("div", class_="amount_info_container")
    if amount_container:
        per_item_table = amount_container.find("table")
        if per_item_table and per_item_table.find("tbody"):
            rows = per_item_table.find("tbody").find_all("tr")[1:]  # skip header row
            for r in rows:
                tds = r.find_all("td")
                if len(tds) != 2:
                    continue
                label = tds[0].get_text(strip=True)
                if label == "Total" or "Commission de vente" in label:
                    continue
                jp_shipping_by_id[label] = _parse_jpy(tds[1].get_text(strip=True))

        totals_dl = amount_container.find("dl")
        if totals_dl:
            dts = totals_dl.find_all("dt")
            dds = totals_dl.find_all("dd")
            for dt, dd in zip(dts, dds):
                label = dt.get_text(strip=True)
                if "Frais de port internationaux" in label:
                    international_shipping_jpy = _parse_jpy(dd.get_text(strip=True))
                elif "totaux" in label.lower() and "expedition" in label.lower():
                    international_shipping_eur_buyee = _parse_eur_from_text(
                        dd.get_text(" ", strip=True)
                    )
    else:
        warnings.append(
            "Un colis Buyee n'a pas de detail des frais de port "
            "(div.amount_info_container introuvable)."
        )

    # Buyee bills ONE combined international shipping fee for the whole
    # package, never per item -- split it evenly across the items it
    # contains as a reasonable approximation the user can still edit.
    n_items = len(items) or 1
    intl_share_jpy = international_shipping_jpy / n_items if international_shipping_jpy else 0.0
    intl_share_eur = (
        international_shipping_eur_buyee / n_items if international_shipping_eur_buyee else None
    )
    if international_shipping_jpy and n_items > 1:
        warnings.append(
            f"Frais de port international Buyee ({international_shipping_jpy:.0f} YENS) "
            f"reparti a parts egales entre les {n_items} articles d'un meme colis "
            "-- ajustable dans la fiche de chaque article."
        )

    for it in items:
        it["japan_domestic_shipping_jpy"] = (
            jp_shipping_by_id.get(it["item_id"], 0.0) if it["item_id"] else 0.0
        )
        it["international_shipping_jpy"] = intl_share_jpy
        it["international_shipping_eur_buyee"] = intl_share_eur

    return items, warnings


def _parse_fiche_html(html: str, fiche_url: str) -> dict:
    """Extracts the photo and the exact price actually billed for one item
    from a 'Fiche complete' order-detail page's HTML, plus Buyee's own
    JPY->EUR conversion when the account has that feature enabled."""
    details: dict = {"photo_url": None, "item_price_jpy": 0.0, "buyee_price_eur": None}
    soup = BeautifulSoup(html, "html.parser")

    img = soup.select_one("div.itemCard__item img.g-thumbnail__image")
    if img and img.get("src"):
        details["photo_url"] = urljoin(fiche_url, img["src"])

    price_block = soup.find("div", class_="g-priceDetails")
    if price_block:
        total_el = price_block.select_one(".g-priceDetails__priceTotal .g-price")
        fx_el = price_block.select_one(".g-priceDetails__priceTotal .g-priceFx")
        if total_el:
            details["item_price_jpy"] = _parse_jpy(total_el.get_text(strip=True))
        if fx_el:
            details["buyee_price_eur"] = _parse_eur_from_text(fx_el.get_text(strip=True))

    return details


def _fetch_item_details(session, fiche_url: str) -> dict:
    """Visits one 'Fiche complete' order-detail page using an already-open
    session (browser or HTTP adapter, both expose .fetch())."""
    try:
        resp = session.fetch(fiche_url)
    except Exception as exc:  # noqa: BLE001 - keep going, one bad item shouldn't fail the import
        logger.warning("Echec du chargement de la fiche %s: %s", fiche_url, exc)
        return {"photo_url": None, "item_price_jpy": 0.0, "buyee_price_eur": None}
    return _parse_fiche_html(str(resp.html_content), fiche_url)


def _fetch_item_details_fresh_browser(cookies: list, fiche_url: str) -> dict:
    """Visits one 'Fiche complete' page in its OWN short-lived browser
    session (a fresh Chromium process per item) instead of reusing one
    long-lived session across every item. Render's own memory metrics
    showed usage climbing with each successive page navigation inside a
    single browser session until it exceeded the 512MB instance limit and
    got OOM-killed mid-import (see the big comment in fetch_invoices) --
    opening and fully closing a new browser per item means Chromium's
    memory is handed back to the OS between items instead of accumulating.
    Slower (every item pays a fresh browser-launch cost, roughly 1-3s) but
    far less likely to get killed partway through."""
    from scrapling.fetchers import DynamicSession

    try:
        with DynamicSession(
            headless=True,
            network_idle=True,
            disable_resources=True,
            cookies=cookies or [],
        ) as fiche_browser:
            resp = fiche_browser.fetch(fiche_url)
            return _parse_fiche_html(str(resp.html_content), fiche_url)
    except Exception as exc:  # noqa: BLE001 - one bad item shouldn't fail the whole import
        logger.warning("Echec du chargement de la fiche %s: %s", fiche_url, exc)
        return {"photo_url": None, "item_price_jpy": 0.0, "buyee_price_eur": None}


def _page_diagnostic(resp) -> str:
    """A short 'where did we actually end up' string (URL + title) used to
    tell apart, from the warnings shown in the app, whether a failed import
    is a login problem, a bot-detection/redirect problem, or a genuinely
    empty account -- without needing another round-trip of HTML files."""
    try:
        soup = BeautifulSoup(str(resp.html_content), "html.parser")
        title = soup.title.get_text(strip=True) if soup.title else "(sans titre)"
    except Exception:  # noqa: BLE001
        title = "(titre illisible)"
    url = getattr(resp, "url", "(url inconnue)")
    return f"URL={url} | titre={title}"


def _login_looks_successful(html: str, url: str = "") -> bool:
    """Heuristic check that the login actually worked, so a bad selector or
    a wrong/expired password produces a clear warning instead of silently
    trying to scrape a login page and finding nothing.

    CONFIRMED BUG on 2026-09-21: this used to only check for the password
    field being gone, which is ALSO true on Buyee's email-verification
    ("twoFactor") page -- so a login that was actually still pending a
    verification code was wrongly reported as successful, and the scrape
    went on to hit the Colis page with an unauthenticated session (which
    Buyee just redirects back to /signup/login, producing "aucun colis
    trouve" instead of a clear "code needed" message)."""
    if "twofactor" in url.lower() or "two_factor" in url.lower() or "certification" in url.lower():
        return False
    soup = BeautifulSoup(html, "html.parser")
    if soup.select_one(LOGIN_SELECTORS["password_field"]):
        return False  # still looking at a login form
    if soup.find("a", href=re.compile(r"/mypage")):
        return True
    return True  # give the benefit of the doubt; the baggages page check below is authoritative


def _describe_input_fields(html: str) -> str:
    """Lists every <input>'s name/id/type/placeholder on a page -- used as
    a diagnostic when we land on what looks like a verification/2FA page
    but none of our guessed VERIFICATION_CODE_FIELD_CANDIDATES matched, so
    the real field can be identified from the app's own warnings instead
    of needing another saved-HTML upload."""
    soup = BeautifulSoup(html, "html.parser")
    fields = []
    for inp in soup.find_all("input"):
        if inp.get("type") == "hidden":
            continue
        fields.append(
            f"(name={inp.get('name')!r} id={inp.get('id')!r} type={inp.get('type')!r} "
            f"placeholder={inp.get('placeholder')!r})"
        )
    return "; ".join(fields) if fields else "(aucun champ input visible trouve)"


def _describe_clickable_elements(html: str) -> str:
    """Lists every <button> and <a> on a page (id/class/text) -- same idea
    as _describe_input_fields, but for the submit control : Buyee's
    "Login" button on the main login page turned out to be a plain <a>
    wired up by JS rather than a real <button>/<input type=submit> (see
    SUBMIT_BUTTON_CANDIDATES above), so a different page (like the
    twoFactor code page) may well use yet another pattern our existing
    candidates don't match."""
    soup = BeautifulSoup(html, "html.parser")
    elements = []
    for tag_name in ("button", "a", "input"):
        for el in soup.find_all(tag_name):
            if tag_name == "input" and el.get("type") not in ("submit", "button"):
                continue
            text = el.get_text(strip=True)[:40]
            elements.append(
                f"<{tag_name} id={el.get('id')!r} class={el.get('class')!r} "
                f"texte={text!r}>"
            )
    return "; ".join(elements) if elements else "(aucun bouton/lien trouve)"


# CONFIRMED on 2026-09-21 against the real twoFactor page (via the
# _describe_input_fields diagnostic below): Buyee splits the 6-digit
# verification code into 6 separate single-character text boxes with ids
# input1..input6, instead of one field matching VERIFICATION_CODE_FIELD_CANDIDATES
# (that list is kept in case Buyee ever uses a single-field layout for some
# accounts/locales).
CODE_BOX_INPUT_IDS = [f"input{i}" for i in range(1, 7)]


def fetch_invoices(credentials: BuyeeCredentials, max_items: int = 8) -> ScrapeResult:
    """Logs into Buyee and pulls recent shipped packages: article name,
    photo, item price, Japan domestic shipping AND the real international
    (Japan -> France) shipping fee Buyee already charged, for each line
    item.

    Uses Scrapling's DynamicSession (a real, scriptable Chromium browser)
    because Buyee's login form and account pages are JS-rendered, and
    BeautifulSoup to parse the resulting HTML (Scrapling's own selector API
    is fine for simple lookups, but this page's nested toggle panels and
    label/value tables are much clearer to express with BeautifulSoup).
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

    login_debug: dict = {
        "username_selector": None,
        "password_selector": None,
        "submit_selector": None,
        "verification_field_selector": None,
        "verification_submit_selector": None,
        "cookies": None,
        "user_agent": None,
        "error": None,
    }

    def _fill_first_match(page, candidates: list[str], value: str) -> str | None:
        for sel in candidates:
            try:
                page.fill(sel, value, timeout=FIELD_TRY_TIMEOUT_MS)
                return sel
            except Exception:  # noqa: BLE001 - just try the next candidate
                continue
        return None

    def _click_first_match(page, candidates: list[str]) -> str | None:
        """CONFIRMED BUG on 2026-09-21: clicking Buyee's login button
        triggers an immediate navigation (to /signup/login or straight to
        /signup/twoFactor), and Playwright's page.click() can raise
        "Execution context was destroyed" when the page it's clicking on
        navigates away before its own post-click bookkeeping finishes --
        even though the click itself worked perfectly. Without
        no_wait_after=True, that exception was being swallowed by the
        except below and treated as "button not found", which made the
        code miss the two-factor page entirely (it looked like total
        failure when login had actually succeeded). no_wait_after=True
        makes the click return immediately instead of waiting on the
        navigation it just triggered; the explicit wait_for_load_state
        call right after this function's callers handles waiting for that
        navigation instead."""
        for sel in candidates:
            try:
                page.click(sel, timeout=FIELD_TRY_TIMEOUT_MS, no_wait_after=True)
                return sel
            except Exception:  # noqa: BLE001
                continue
        return None

    def _find_first_present(page, candidates: list[str]) -> str | None:
        """Like _fill_first_match but read-only: just checks whether one of
        these selectors exists on the page right now, without touching it."""
        for sel in candidates:
            try:
                if page.query_selector(sel):
                    return sel
            except Exception:  # noqa: BLE001
                continue
        return None

    def _find_code_boxes(page) -> list[str]:
        """CONFIRMED on 2026-09-21: Buyee's twoFactor page doesn't have one
        code field -- it splits the 6-digit code into 6 separate
        single-character boxes with ids input1..input6. Returns the ids
        that are actually present right now, or an empty list."""
        present = []
        for box_id in CODE_BOX_INPUT_IDS:
            try:
                if page.query_selector(f"#{box_id}"):
                    present.append(box_id)
            except Exception:  # noqa: BLE001
                continue
        return present

    def _capture_session(page) -> None:
        """Grabs the logged-in cookies + the real browser's user agent so
        the rest of the scrape can use a plain, lightweight HTTP session
        instead of keeping the whole (memory-hungry) browser open."""
        try:
            login_debug["cookies"] = page.context.cookies()
            login_debug["user_agent"] = page.evaluate("() => navigator.userAgent")
        except Exception:  # noqa: BLE001
            login_debug["cookies"] = []
            login_debug["user_agent"] = None

    def _do_login(page):
        """Runs inside Scrapling's browser via page_action: receives the
        real Playwright Page object to fill and submit the login form.
        Tries several likely selectors quickly (a few seconds each) instead
        of betting everything on one guess for 30s, and records which ones
        worked (or that none did) in login_debug for the warnings below.
        Also handles Buyee's optional email-verification-code step (see
        VERIFICATION_CODE_FIELD_CANDIDATES above)."""
        login_debug["username_selector"] = _fill_first_match(
            page, USERNAME_FIELD_CANDIDATES, credentials.username
        )
        if not login_debug["username_selector"]:
            login_debug["error"] = "champ identifiant introuvable"
            return
        login_debug["password_selector"] = _fill_first_match(
            page, PASSWORD_FIELD_CANDIDATES, credentials.password
        )
        if not login_debug["password_selector"]:
            login_debug["error"] = "champ mot de passe introuvable"
            return
        login_debug["submit_selector"] = _click_first_match(page, SUBMIT_BUTTON_CANDIDATES)
        if not login_debug["submit_selector"]:
            login_debug["error"] = "bouton de connexion introuvable"
            return
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:  # noqa: BLE001 - not fatal, we check the resulting page below anyway
            pass

        verification_selector = _find_first_present(page, VERIFICATION_CODE_FIELD_CANDIDATES)
        code_boxes = _find_code_boxes(page) if not verification_selector else []
        if verification_selector or code_boxes:
            login_debug["verification_field_selector"] = (
                verification_selector
                if verification_selector
                else f"#{code_boxes[0]}..#{code_boxes[-1]} (6 cases separees)"
            )
            if not credentials.verification_code:
                login_debug["error"] = "code_de_verification_requis"
                return
            code_digits = "".join(ch for ch in credentials.verification_code if ch.isdigit())
            if verification_selector:
                page.fill(verification_selector, code_digits, timeout=FIELD_TRY_TIMEOUT_MS)
            elif len(code_digits) < len(code_boxes):
                login_debug["error"] = (
                    f"code_de_verification_incomplet ({len(code_digits)} chiffres recus, "
                    f"{len(code_boxes)} cases attendues)"
                )
                return
            else:
                # CONFIRMED BUG on 2026-09-21: page.fill() sets each box's
                # value directly via JS and only fires "input"/"change" --
                # it does NOT fire real keydown/keypress/keyup events. The
                # diagnostic dump of this page's buttons/links (sent back
                # to the user) showed no plausible "validate the code"
                # button at all -- just the cookie banner, Google Translate
                # widget and language switcher -- which strongly suggests
                # this is a 6-box OTP widget that auto-advances focus and
                # auto-submits on the 6th real keystroke, the same way a
                # phone's own OTP autofill UI works. page.fill() never
                # triggers that JS, so the code was silently never
                # submitted at all. Using a real click + keyboard.type()
                # per box fires proper key events, which this kind of
                # widget listens for.
                for box_id, digit in zip(code_boxes, code_digits):
                    try:
                        page.click(f"#{box_id}", timeout=FIELD_TRY_TIMEOUT_MS)
                        page.keyboard.type(digit, delay=80)
                    except Exception:  # noqa: BLE001 - fall back to a direct
                        # value-set for this one box rather than aborting
                        # the whole code entry over one flaky box.
                        page.fill(f"#{box_id}", digit, timeout=FIELD_TRY_TIMEOUT_MS)
                # Give any auto-advance/auto-submit JS triggered by that
                # last keystroke a brief moment to run before we check.
                page.wait_for_timeout(800)
                # Fallback in case this widget needs an explicit submit
                # instead of (or in addition to) auto-submitting: try
                # Enter first (common for OTP forms), then any of our
                # known button candidates (harmless no-op if neither
                # exists / already submitted).
                try:
                    page.keyboard.press("Enter")
                except Exception:  # noqa: BLE001
                    pass
                login_debug["verification_submit_selector"] = _click_first_match(page, SUBMIT_BUTTON_CANDIDATES)
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:  # noqa: BLE001
                pass

        _capture_session(page)

    # NOTE: Scrapling's StealthySession (a stealth/"patchright" browser that
    # can look more like a normal Chrome tab and push through Cloudflare)
    # was tried here but needs a newer bundled Chromium than this Docker
    # image ships -- it crashed with "Executable doesn't exist at
    # /ms-playwright/chromium-1234/...". Sticking with DynamicSession for
    # now (proven to run in this image); revisit stealth mode -- and bump
    # the Dockerfile's playwright/python base image tag to match -- only if
    # the diagnostics below actually point to bot detection.
    # disable_resources=True stops the browser from downloading images,
    # fonts, stylesheets and media (it still runs all JavaScript, which is
    # what actually renders the Knockout.js price/photo data we need) --
    # this was added after Render's own memory metrics showed the process
    # climbing from ~58MB to ~536MB (the instance's 512MB limit) during a
    # real import and getting OOM-killed mid-request, which is what showed
    # up in the app as "Failed to fetch". We only ever read the *URL*
    # string out of each <img src="..."> attribute, never the decoded
    # image itself, so not fetching the actual image bytes costs nothing.
    with DynamicSession(headless=True, network_idle=True, disable_resources=True) as session:
        login_result = session.fetch(BUYEE_LOGIN_URL, page_action=_do_login)
        warnings.append(
            f"[diagnostic] Selecteurs de connexion utilises : "
            f"identifiant={login_debug['username_selector']!r}, "
            f"mot_de_passe={login_debug['password_selector']!r}, "
            f"bouton={login_debug['submit_selector']!r}"
        )
        warnings.append(f"[diagnostic] Apres connexion : {_page_diagnostic(login_result)}")
        if login_debug["verification_field_selector"]:
            warnings.append(
                f"[diagnostic] Code de verification : champ={login_debug['verification_field_selector']!r}, "
                f"bouton={login_debug['verification_submit_selector']!r}"
            )

        if login_debug["error"] == "code_de_verification_requis":
            warnings.append(
                "Buyee demande un code de verification recu par email (verifie ta boite "
                "mail, y compris les spams -- l'objet mentionne une 'connexion douteuse'). "
                "Renseigne ce code dans le champ prevu et reessaie l'import ; tes "
                "identifiants sont corrects, il ne manque que ce code."
            )
            return ScrapeResult(articles=[], warnings=warnings)

        if login_debug["error"] and login_debug["error"].startswith("code_de_verification_incomplet"):
            warnings.append(
                f"Le code de verification saisi ne fait pas 6 chiffres ({login_debug['error']}). "
                "Buyee attend un code a 6 chiffres recu par email -- reessaie en copiant le code "
                "exact du dernier email 'connexion douteuse'."
            )
            return ScrapeResult(articles=[], warnings=warnings)

        login_url_after = str(login_result.url or "")
        login_ok = not login_debug["error"] and _login_looks_successful(
            str(login_result.html_content), login_url_after
        )
        looks_like_verification_page = any(
            token in login_url_after.lower()
            for token in ("twofactor", "two_factor", "certification")
        )
        if login_debug["error"]:
            warnings.append(
                f"La connexion a Buyee a echoue avant meme d'envoyer le formulaire : "
                f"{login_debug['error']}. Il faut ajuster les selecteurs de connexion "
                f"dans buyee_scraper.py (USERNAME_FIELD_CANDIDATES / "
                f"PASSWORD_FIELD_CANDIDATES / SUBMIT_BUTTON_CANDIDATES) -- envoie le HTML "
                f"de https://buyee.jp/signup/login (deconnectee) pour que je trouve les bons."
            )
        elif not login_ok and looks_like_verification_page and not login_debug["verification_field_selector"]:
            # On est bien arrive sur la page de code de verification (2FA)
            # Buyee, mais aucun des VERIFICATION_CODE_FIELD_CANDIDATES ni le
            # motif a 6 cases (CODE_BOX_INPUT_IDS) n'a ete trouve pendant
            # _do_login -- donc le code (meme fourni) n'a jamais pu etre
            # saisi. On liste tous les champs <input> visibles de cette page
            # dans un warning pour identifier le vrai champ sans devoir
            # re-uploader un fichier HTML.
            warnings.append(
                "Buyee a redirige vers sa page de code de verification (2FA), mais "
                "aucun champ de saisie connu n'a ete trouve pour y entrer le code -- "
                "il faut ajuster VERIFICATION_CODE_FIELD_CANDIDATES ou CODE_BOX_INPUT_IDS "
                "dans buyee_scraper.py. Champs <input> visibles trouves sur cette page : "
                f"{_describe_input_fields(str(login_result.html_content))}"
            )
        elif not login_ok and looks_like_verification_page:
            # Le champ (ou les 6 cases) du code ONT ete trouves et remplis,
            # et un clic sur SUBMIT_BUTTON_CANDIDATES a ete tente
            # (verification_submit_selector), mais on est toujours sur la
            # page de verification -- soit le code etait deja expire (Buyee
            # en emet un nouveau a chaque tentative de connexion), soit ce
            # clic n'a pas vise le vrai bouton de validation de cette page.
            # On liste les boutons/liens presents pour trouver le bon.
            warnings.append(
                "Le code de verification a ete saisi mais Buyee est reste sur la page de "
                "verification -- soit ce code est expire (Buyee en renvoie un nouveau a "
                "chaque tentative : utilise le DERNIER email recu, pas un ancien), soit le "
                f"bouton de validation utilise ({login_debug['verification_submit_selector']!r}) "
                "n'etait pas le bon. Boutons/liens visibles sur cette page : "
                f"{_describe_clickable_elements(str(login_result.html_content))}"
            )
        elif not login_ok:
            warnings.append(
                "La connexion a Buyee semble avoir echoue (toujours sur une page de "
                "connexion apres l'envoi du formulaire) -- verifie tes identifiants, "
                "ou envoie le HTML de https://buyee.jp/signup/login (deconnectee) pour "
                "que je verifie les selecteurs."
            )

        if not login_ok:
            # Don't burn several more minutes (and risk the request timing
            # out entirely, which shows up in the app as a generic "Failed
            # to fetch") trying to scrape a page we know we're not logged
            # into.
            return ScrapeResult(articles=[], warnings=warnings)

        cookies = login_debug.get("cookies") or []
        user_agent = login_debug.get("user_agent") or DEFAULT_USER_AGENT
    # The browser used for login is now fully closed (we've left the `with`
    # block), which is when most of the memory it used gets freed.

    # --- Colis list: plain HTTP, no browser -----------------------------
    # Confirmed against real saved HTML: the shipping-fee/delivery panels on
    # this page are plain server-rendered HTML (values sit directly inside
    # <td>/<dd> tags, no Knockout data-bind attribute on them) just visually
    # hidden with CSS -- unlike the Fiche complete page below, no JavaScript
    # needs to run for this data to be present, so a lightweight HTTP
    # session (using the cookies captured during login) is enough. This is
    # the fix for the OOM crashes: the real browser no longer has to stay
    # open through the whole multi-page scrape, only for the login step and
    # briefly per item below.
    http_session = requests.Session()
    for c in cookies:
        try:
            http_session.cookies.set(
                c.get("name"), c.get("value"), domain=c.get("domain"), path=c.get("path", "/")
            )
        except Exception:  # noqa: BLE001
            continue
    http_session.headers.update({"User-Agent": user_agent, "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8"})
    list_session = _HttpSessionAdapter(http_session)

    raw_items: list[dict] = []
    page_num = 1
    while len(raw_items) < max_items and page_num <= MAX_BAGGAGE_PAGES:
        list_url = BUYEE_BAGGAGES_URL_TEMPLATE.format(page=page_num)
        resp = list_session.fetch(list_url)
        soup = BeautifulSoup(str(resp.html_content), "html.parser")
        packages = soup.find_all("li", class_="luggageInfo")
        if not packages:
            if page_num == 1:
                warnings.append(f"[diagnostic] Page colis : {_page_diagnostic(resp)}")
                warnings.append(
                    "Aucun colis trouve sur ta page 'Colis expedies' Buyee "
                    "(https://buyee.jp/mybaggages/shipped/1). Si tu as des achats "
                    "encore en cours (pas encore expedies), ils n'apparaissent pas "
                    "encore ici -- c'est normal, Buyee ne facture les frais de port "
                    "internationaux qu'une fois le colis expedie."
                )
            break
        for pkg in packages:
            items, pkg_warnings = _parse_package(pkg)
            warnings.extend(pkg_warnings)
            raw_items.extend(items)
        page_num += 1

    raw_items = raw_items[:max_items]

    # --- Fiche complete pages: one short-lived browser per item ----------
    # This page IS Knockout.js-rendered (data-bind attributes on the price
    # spans), so it does need a real browser with JavaScript -- but a fresh
    # one per item, immediately closed afterwards, so memory never
    # accumulates across items the way it did before (see
    # _fetch_item_details_fresh_browser's docstring).
    for it in raw_items:
        details = {"photo_url": None, "item_price_jpy": 0.0, "buyee_price_eur": None}
        if it.get("fiche_url"):
            details = _fetch_item_details_fresh_browser(cookies, it["fiche_url"])

        articles.append(
            Article(
                id=new_id(),
                source_invoice_id=it.get("order_number") or it.get("item_id") or new_id(),
                name=it["name"],
                photo_url=details["photo_url"],
                item_price_jpy=details["item_price_jpy"] or 0.0,
                japan_domestic_shipping_jpy=it["japan_domestic_shipping_jpy"],
                international_shipping_jpy=it["international_shipping_jpy"],
                international_shipping_eur=(
                    it["international_shipping_eur_buyee"]
                ),
                buyee_price_eur=details["buyee_price_eur"],
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
            international_shipping_jpy=3500,
            international_shipping_eur=20.5,
            buyee_price_eur=27.5,
            category="toys_figures",
        ),
        Article(
            id=new_id(),
            source_invoice_id="demo-invoice-1",
            name="Coffret cartes One Piece OP-07 (scelle)",
            photo_url="https://picsum.photos/seed/onepiece/400/400",
            item_price_jpy=6200,
            japan_domestic_shipping_jpy=600,
            international_shipping_jpy=3500,
            international_shipping_eur=20.5,
            buyee_price_eur=35.6,
            category="trading_cards",
        ),
    ]
    return ScrapeResult(
        articles=sample,
        warnings=[
            "Donnees de demonstration -- branche fetch_invoices() avec tes vrais identifiants "
            "pour remplacer ces exemples par tes factures reelles."
        ],
    )
