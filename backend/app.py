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
from datetime import datetime, timezone

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


def _ms_iso(ms):
    """Retell sends start/end as epoch milliseconds; our columns are timestamptz."""
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat() if ms else None


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

    # Which practice is this call for? The practice's own number is the dialled (to) number on an
    # inbound call, but the caller (from) number on an outbound one. Resolve from the dialled end
    # first, then fall back to the other end, so routing works in both directions.
    to_number = _extract_to_number(body)
    from_number = _extract_from_number(body)
    # Resolving the tenant builds its PMS (which may reach Supabase / Google). Never let a misconfig
    # 500 the whole endpoint — return a clean error the agent can fall back on.
    try:
        tenant = get_tenant(to_number) or (get_tenant(from_number) if from_number else None)
        if tenant is None:
            # Neither end is registered to a practice. This is the usual cause of a call where every
            # function "can't reach the system" — log it so it isn't read as an outage.
            print(f"WARNING: no tenant for call to={to_number!r} from={from_number!r} "
                  f"— register the practice number in `tenants`.")
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


# Retell's agent-level webhook (call_started / call_ended / call_analyzed). Defined BEFORE the
# /webhook/{function} catch-all so it isn't swallowed by it. Retell's agent webhook can't send our
# custom header, so the shared secret rides in the URL as ?token=<secret>.
@app.post("/webhook/call-event")
async def call_event(request: Request):
    if WEBHOOK_SECRET and request.query_params.get("token") != WEBHOOK_SECRET:
        return JSONResponse(status_code=401,
                            content={"status": "error", "message": "unauthorized"})
    body = await request.json()
    call = body.get("call") or body          # the webhook wraps the call object under "call"
    call_id = call.get("call_id")
    if not call_id or not store.configured():
        return {"status": "ignored"}
    try:
        store.enrich_call_log(
            call_id,
            transcript=call.get("transcript"),
            recording_url=call.get("recording_url"),
            started_at=_ms_iso(call.get("start_timestamp")),
            ended_at=_ms_iso(call.get("end_timestamp")),
            from_number=call.get("from_number"),
            to_number=call.get("to_number"))
    except Exception:
        traceback.print_exc()
    return {"status": "ok"}


@app.post("/webhook/{function}")
async def webhook_named(function: str, request: Request):
    return await _handle(request, path_function=function)


# Pinned to 8080 so we never collide with the AskMyDocs app on 8000.
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8080, reload=True)
