from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import sys
import threading
import traceback
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException

from .. import storage
from ..buyee_scraper import fetch_invoices_demo
from ..models import Article, BuyeeCredentials, VerificationCodeSubmission

logger = logging.getLogger("buy_setup")

router = APIRouter(prefix="/invoices", tags=["invoices"])

# CONFIRMED BUG on 2026-09-21: a real import against Buyee's twoFactor page
# was observed to hang forever inside Scrapling/Playwright (memory stayed
# high indefinitely instead of dropping back down, and no request ever
# completed, even after several minutes) -- almost certainly a Chromium
# child process leaking every time this happened. Because the whole scrape
# used to run in-process inside this request handler, the phone's own
# connection would eventually give up ("Failed to fetch") long before the
# backend did, while the backend kept the browser open forever in the
# background, accumulating leaked memory across attempts (each attempt
# left the service's baseline memory usage a bit higher than before).
#
# Fix, in two parts:
# 1. The scrape now runs in a completely separate OS process (not a thread,
#    not an in-process browser) so that if it ever hangs again, it can be
#    forcibly killed -- process group and all, so any Chromium child dies
#    with it -- instead of leaking memory forever. See buyee_import_worker.py.
# 2. That process runs in a background thread instead of inside the HTTP
#    request itself, and the request returns a job_id immediately. The
#    frontend polls GET /invoices/import/{job_id} every few seconds instead
#    of keeping one HTTP request open for up to several minutes -- which is
#    exactly the kind of long-lived request a phone's network, a proxy, or
#    the browser itself can silently cut off, showing "Failed to fetch"
#    even when the backend would otherwise have succeeded a bit later.
#
# CONFIRMED ROOT CAUSE #2 on 2026-09-21: Buyee issues a brand-new one-time
# verification code by email on EVERY login attempt, so the original
# single-request design (username+password+code all at once) could never
# work -- by the time the user had the code in hand, a fresh attempt with
# it would already be invalidating it. Import is therefore now a two-phase
# job:
#   POST /invoices/import           -- phase 1, username+password only.
#   POST /invoices/import/{id}/verify -- phase 2, just the code, resuming
#                                        the SAME pending session captured
#                                        by phase 1 (its cookies are kept
#                                        here, server-side, in the job
#                                        dict -- never sent back to the
#                                        client).
# Both phases share the same GET /invoices/import/{id} polling endpoint and
# the same background-worker-process machinery.
IMPORT_PROCESS_TIMEOUT_SECONDS = 240

# The worker must be launched with the backend's own root directory (the
# one containing the `app` package) as cwd, i.e. two levels up from this
# file (app/routers/invoices.py -> app/routers -> app -> backend root).
# CONFIRMED BUG on 2026-09-21: this used to be hardcoded to "/app" (the
# Docker image's WORKDIR), which raised FileNotFoundError anywhere else
# (e.g. running the test suite locally) -- and because that Popen() call
# happened outside of the try/except below, the exception silently killed
# the whole background thread, leaving the job stuck at "running" forever
# with no error ever recorded. Computing the path instead of hardcoding it
# fixes the real bug; wrapping the whole function body in try/except
# (below) makes sure that *no* future surprise here can ever again leave a
# job stuck at "running" forever.
_BACKEND_ROOT = Path(__file__).resolve().parents[2]

_import_jobs: dict[str, dict] = {}
_import_jobs_lock = threading.Lock()


def _set_job(job_id: str, job: dict) -> None:
    with _import_jobs_lock:
        _import_jobs[job_id] = job


def _run_worker(job_id: str, payload: dict) -> None:
    """Runs buyee_import_worker.py (either mode="login" or mode="verify",
    see that file's docstring) with `payload` as its stdin JSON, and
    updates _import_jobs[job_id] from whatever it prints. Shared by both
    the initial username+password phase and the verification-code phase,
    since the worker's output shape is identical for both."""
    try:
        proc = subprocess.Popen(
            [sys.executable, "-m", "app.buyee_import_worker"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(_BACKEND_ROOT),
            start_new_session=True,  # own process group, so a timeout kill
            # below also takes down any Chromium child process this worker
            # spawned, instead of leaving it running and leaking memory
            # forever.
        )
    except Exception as exc:  # noqa: BLE001 - see _BACKEND_ROOT comment above
        logger.error("Import Buyee : impossible de demarrer le worker (job %s) :\n%s", job_id, traceback.format_exc())
        _set_job(job_id, {
            "status": "error",
            "detail": f"Impossible de demarrer le processus d'import ({exc.__class__.__name__}: {exc}).",
        })
        return

    try:
        try:
            stdout, stderr = proc.communicate(
                input=json.dumps(payload),
                timeout=IMPORT_PROCESS_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                proc.wait(timeout=5)
            except Exception:  # noqa: BLE001
                pass
            logger.error("Import Buyee : timeout apres %ss (job %s)", IMPORT_PROCESS_TIMEOUT_SECONDS, job_id)
            _set_job(job_id, {
                "status": "error",
                "detail": (
                    f"L'import a pris plus de {IMPORT_PROCESS_TIMEOUT_SECONDS}s et a ete "
                    "arrete automatiquement. Reessaie -- si ca se reproduit, c'est "
                    "probablement Buyee ou le serveur gratuit qui sont juste lents "
                    "en ce moment, pas tes identifiants."
                ),
            })
            return

        if proc.returncode != 0:
            logger.error(
                "Import Buyee : le worker a echoue (code %s, job %s) :\n%s",
                proc.returncode, job_id, stderr,
            )
            _set_job(job_id, {
                "status": "error",
                "detail": (
                    "Impossible de recuperer les factures Buyee "
                    f"(le processus d'import s'est arrete avec le code {proc.returncode}). "
                    "Verifie tes identifiants, ou utilise 'Charger des donnees de demo' "
                    "en attendant que le scraper soit ajuste."
                ),
            })
            return

        try:
            last_line = [line for line in stdout.splitlines() if line.strip()][-1]
            result = json.loads(last_line)
        except Exception as exc:  # noqa: BLE001
            logger.error("Import Buyee : reponse illisible (job %s) : %r\nstderr:\n%s", job_id, stdout, stderr)
            _set_job(job_id, {
                "status": "error",
                "detail": f"Reponse d'import illisible ({exc.__class__.__name__}: {exc}).",
            })
            return

        if result.get("status") == "code_required":
            # Pending 2FA: keep the session's cookies server-side only (key
            # prefixed with "_" so the GET endpoint below strips it before
            # ever returning the job to the client) until the user submits
            # the code via POST /invoices/import/{job_id}/verify.
            _set_job(job_id, {
                "status": "code_required",
                "warnings": result.get("warnings", []),
                "_session_cookies": result.get("session_cookies"),
                "_session_user_agent": result.get("session_user_agent"),
            })
            return

        saved = storage.upsert_articles(result["articles"])
        _set_job(job_id, {
            "status": "done",
            "articles": saved,
            "warnings": result.get("warnings", []),
        })
    except Exception as exc:  # noqa: BLE001 - absolute last resort: a job must
        # NEVER be left stuck at "running" forever because of an exception
        # we didn't anticipate here.
        logger.error("Import Buyee : erreur inattendue (job %s) :\n%s", job_id, traceback.format_exc())
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except Exception:  # noqa: BLE001
            pass
        _set_job(job_id, {
            "status": "error",
            "detail": f"Erreur inattendue pendant l'import ({exc.__class__.__name__}: {exc}).",
        })


@router.post("/import")
def import_invoices(credentials: BuyeeCredentials):
    """Starts phase 1 of a Buyee import (username+password only) in the
    background and returns immediately with a job_id ; poll
    GET /invoices/import/{job_id} for the result. If Buyee then asks for an
    emailed verification code, that GET response comes back with
    status=="code_required" -- submit the code via
    POST /invoices/import/{job_id}/verify (NOT by calling this endpoint
    again, which would trigger a brand new login and a brand new code).
    Credentials are only ever kept in memory / passed over a pipe to the
    worker process, never written to disk, logged, or persisted, and are
    discarded once the worker process exits."""
    job_id = uuid.uuid4().hex
    _set_job(job_id, {"status": "running"})
    thread = threading.Thread(
        target=_run_worker,
        args=(job_id, {"mode": "login", "username": credentials.username, "password": credentials.password}),
        daemon=True,
    )
    thread.start()
    return {"job_id": job_id, "status": "running"}


@router.post("/import/{job_id}/verify")
def verify_import(job_id: str, submission: VerificationCodeSubmission):
    """Phase 2: submits the verification code Buyee just emailed for the
    pending login started by POST /invoices/import. Resumes that EXACT
    session (via cookies kept server-side on the job, never exposed to the
    client) instead of logging in again -- see buyee_scraper.py's
    _login_phase1 docstring for why a fresh login here would always
    invalidate the code. Returns immediately with the job back in
    status=="running" ; keep polling GET /invoices/import/{job_id}."""
    with _import_jobs_lock:
        job = _import_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Import introuvable (job_id inconnu ou expire).")
    if job.get("status") != "code_required":
        raise HTTPException(
            status_code=409,
            detail="Cet import n'attend pas de code de verification pour le moment.",
        )
    payload = {
        "mode": "verify",
        "session_cookies": job.get("_session_cookies"),
        "session_user_agent": job.get("_session_user_agent"),
        "verification_code": submission.verification_code,
    }
    _set_job(job_id, {"status": "running"})
    thread = threading.Thread(target=_run_worker, args=(job_id, payload), daemon=True)
    thread.start()
    return {"job_id": job_id, "status": "running"}


@router.get("/import/{job_id}")
def get_import_status(job_id: str):
    with _import_jobs_lock:
        job = _import_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Import introuvable (job_id inconnu ou expire).")
    if job["status"] == "error":
        raise HTTPException(status_code=502, detail=job["detail"])
    # Never expose the pending session's cookies to the client -- keys
    # prefixed with "_" are internal-only (see _run_worker above).
    return {k: v for k, v in job.items() if not k.startswith("_")}


@router.post("/demo")
def import_invoices_demo():
    """Loads sample articles so you can try the rest of the app (cost
    calculator, WhatNot strategy, product sheet, sales tracking) without
    needing real Buyee credentials yet."""
    result = fetch_invoices_demo()
    saved = storage.upsert_articles([a.model_dump(mode="json") for a in result.articles])
    return {"articles": saved, "warnings": result.warnings}


@router.get("")
def list_articles():
    return storage.list_articles()


@router.get("/{article_id}")
def get_article(article_id: str):
    article = storage.get_article(article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article introuvable")
    return article


@router.put("/{article_id}")
def update_article(article_id: str, article: Article):
    if article.id != article_id:
        raise HTTPException(status_code=400, detail="id mismatch")
    saved = storage.upsert_articles([article.model_dump(mode="json")])
    return next(a for a in saved if a["id"] == article_id)
