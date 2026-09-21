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

Protocol: reads one JSON object (a BuyeeCredentials payload) from stdin,
writes one line of JSON (articles + warnings) to stdout, and exits.
Credentials only ever exist in this short-lived process's memory and on
its stdin pipe (never a file, never a log line, never the JSON storage
layer) -- consistent with the privacy guarantee documented on
BuyeeCredentials in models.py."""
from __future__ import annotations

import json
import sys

from app.buyee_scraper import fetch_invoices
from app.models import BuyeeCredentials


def main() -> None:
    raw = sys.stdin.read()
    data = json.loads(raw)
    credentials = BuyeeCredentials(**data)
    result = fetch_invoices(credentials)
    payload = {
        "articles": [a.model_dump(mode="json") for a in result.articles],
        "warnings": result.warnings,
    }
    # Exactly one line of JSON on stdout -- the parent process reads only
    # the last line, so nothing else (a stray print from a dependency,
    # say) written earlier on stdout can corrupt the result.
    print(json.dumps(payload))


if __name__ == "__main__":
    main()
