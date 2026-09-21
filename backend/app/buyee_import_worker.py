"""Standalone worker: run as its own OS process (never as a thread or a
fork inside the main API process) so it can be forcibly killed if it hangs.

CONFIRMED ROOT CAUSE on 2026-09-21: real-world imports against Buyee's
twoFactor (email verification) page were observed to sometimes never
return at all -- Render's memory metrics showed the browser's memory
plateauing indefinitely instead of dropping back down after the page
finished loading, and no request-completion log line ever appeared, even
several minutes later. Something inside Scrapling/Playwright (most likely
around the JS `page.evaluate()` call used to read the browser's user
agent, which has no timeout of its own) can get stuck waiting forever on
that particular page. Each stuck attempt leaked a whole Chromium process
that never got cleaned up, which is why the service's baseline memory
usage kept climbing between attempts instead of returning to normal.

Rather than trying to hunt down and patch that exact hang inside a
third-party library, this worker is run as a completely separate process
(see routers/invoices.py) that the caller can flat-out kill -- process
group and all, so the Chromium child dies too -- after a generous but
bounded timeout. This guarantees the API can never again be stuck with a
leaked browser no matter what causes a future hang, known or not.

CONFIRMED ROOT CAUSE #2 on 2026-09-21: Buyee issues a brand-new one-time
verification code by email on EVERY SINGLE username+password login
attempt. The original single-phase design always re-submitted
username+password before entering whatever code the caller supplied --
so the code, which necessarily came from an OLDER email than the attempt
being made right now, could never be the right one, no matter how
correctly it was typed in. Login is therefore now a two-phase protocol
(see buyee_scraper.py's _login_phase1 / verify_and_fetch_invoices
docstrings for the full story):

  mode="login"  -- username+password only. If Buyee accepts them outright,
                   scrapes and returns the articles. If Buyee shows the
                   verification-code page instead, returns immediately with
                   status="code_required" plus that PENDING session's
                   cookies -- no code is entered in this mode.
  mode="verify" -- resumes that SAME pending session (via the cookies
                   returned above) in a fresh browser navigated straight to
                   the verification page, and enters the code the user just
                   received. Never re-submits username+password, so the
                   code it enters is always for the session that actually
                   generated it.

Protocol: reads one JSON object from stdin, writes one line of JSON to
stdout, and exits.
  {"mode": "login", "username": ..., "password": ...}
  {"mode": "verify", "session_cookies": [...], "session_user_agent": ...,
   "verification_code": "123456"}
Output (both modes): {"status": ..., "articles": [...], "warnings": [...],
"session_cookies": [...] or null, "session_user_agent": ... or null}.

Credentials and session cookies only ever exist in this short-lived
process's memory and on its stdin/stdout pipes (never a file, never a log
line, never the JSON storage layer) -- consistent with the privacy
guarantee documented on BuyeeCredentials in models.py."""
from __future__ import annotations

import json
import sys

from app.buyee_scraper import fetch_invoices, verify_and_fetch_invoices
from app.models import BuyeeCredentials


def _result_payload(result) -> dict:
    return {
        "status": result.status,
        "articles": [a.model_dump(mode="json") for a in result.articles],
        "warnings": result.warnings,
        "session_cookies": result.session_cookies,
        "session_user_agent": result.session_user_agent,
    }


def main() -> None:
    raw = sys.stdin.read()
    data = json.loads(raw)
    mode = data.get("mode", "login")

    if mode == "verify":
        result = verify_and_fetch_invoices(
            session_cookies=data.get("session_cookies") or [],
            session_user_agent=data.get("session_user_agent"),
            verification_code=data.get("verification_code") or "",
        )
    else:
        credentials = BuyeeCredentials(username=data["username"], password=data["password"])
        result = fetch_invoices(credentials)

    payload = _result_payload(result)
    # Exactly one line of JSON on stdout -- the parent process reads only
    # the last line, so nothing else (a stray print from a dependency,
    # say) written earlier on stdout can corrupt the result.
    print(json.dumps(payload))


if __name__ == "__main__":
    main()
