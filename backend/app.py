"""FastAPI app — the front door the voice agent (Retell) calls.

One real endpoint: POST /webhook. It reads the Contract 2 envelope, finds which practice the call
is for (by the dialled number), and routes the function to the right handler. Plus GET /health for
a quick "is it up?" check.

Run locally (port 8080 — 8000 is used by another local app):
    python3 app.py
    # or: uvicorn app:app --reload --port 8080   (from the backend/ directory)
"""

import hmac
import os
import sys
import traceback

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tenants import get_tenant      # noqa: E402
from handlers import dispatch       # noqa: E402
from db import store                # noqa: E402

app = FastAPI(title="Synkris Voice Agent — webhook")

# Shared-secret auth. Retell sends this value in an "X-Webhook-Secret" header on every call; we
# compare it (constant-time) to the WEBHOOK_SECRET env var. If the env var is unset the webhook runs
# OPEN — fine for local dev, but ALWAYS set it on any public/deployed instance.
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET")
if not WEBHOOK_SECRET:
    print("WARNING: WEBHOOK_SECRET not set — /webhook is UNAUTHENTICATED (local dev only).")

# Which practice a call is for is keyed off the dialled number. Depending on how the Retell function
# request body is templated, that number arrives top-level or nested under "call"/"args". Read all
# of those, and fall back to the test practice so dev calls aren't blocked when Retell omits it.
# Override the fallback (or disable it — set to empty) per environment via DEFAULT_TO_NUMBER.
DEFAULT_TO_NUMBER = os.environ.get("DEFAULT_TO_NUMBER", "+441162345678")


def _extract_to_number(body):
    return (
        body.get("to_number")
        or (body.get("call") or {}).get("to_number")
        or (body.get("args") or {}).get("to_number")
        or DEFAULT_TO_NUMBER
    )


def _extract_call_id(body):
    return body.get("call_id") or (body.get("call") or {}).get("call_id")


def _extract_from_number(body):
    return body.get("from_number") or (body.get("call") or {}).get("from_number")


@app.get("/health")
def health():
    # Open, no auth — used by uptime / platform health checks.
    return {"status": "ok"}


async def _handle(request: Request, path_function=None):
    # Reject anyone who doesn't present the shared secret (when one is configured).
    if WEBHOOK_SECRET:
        provided = request.headers.get("x-webhook-secret", "")
        if not hmac.compare_digest(provided, WEBHOOK_SECRET):
            return JSONResponse(status_code=401,
                                content={"status": "error", "message": "unauthorized"})

    body = await request.json()

    # Which practice is this call for? Identified by the number that was dialled.
    to_number = _extract_to_number(body)
    # Resolving the tenant builds its PMS (which may reach Supabase / Google). Never let a misconfig
    # 500 the whole endpoint — return a clean error the agent can fall back on.
    try:
        tenant = get_tenant(to_number)
        if tenant is None:
            return {"status": "error",
                    "message": f"unknown practice for number {to_number}"}

        config, pms = tenant
        # Function identity, most reliable first: the URL path (/webhook/<fn>), then the body. Retell's
        # test dialog overwrites the body's name with "test_tool", so the path is what makes it routable;
        # in our own curls/envelope it comes from "function"/"name".
        function = path_function or body.get("function") or body.get("name")
        result = dispatch(pms, function, body.get("args") or {})
        _log_call(config, body, function, result)
        return result
    except Exception:
        traceback.print_exc()   # full detail in the server logs, not in the response
        return {"status": "error", "message": "Sorry, something went wrong on our side."}


def _log_call(config, body, function, result):
    """Best-effort call log (one row per call_id). Never let logging break the response."""
    call_id = _extract_call_id(body)
    if not store.configured() or not call_id:
        return
    try:
        store.log_call(config["tenant_id"], call_id,
                       _extract_from_number(body), _extract_to_number(body),
                       intent=function or "unknown",
                       outcome=(result or {}).get("status", "unknown"))
    except Exception:
        traceback.print_exc()


@app.post("/webhook")
async def webhook(request: Request):
    return await _handle(request)


@app.post("/webhook/{function}")
async def webhook_named(function: str, request: Request):
    return await _handle(request, path_function=function)


# Pinned to 8080 so we never collide with the AskMyDocs app on 8000.
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8080, reload=True)
