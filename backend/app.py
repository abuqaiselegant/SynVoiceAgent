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

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tenants import get_tenant      # noqa: E402
from handlers import dispatch       # noqa: E402

app = FastAPI(title="Synkris Voice Agent — webhook")

# Shared-secret auth. Retell sends this value in an "X-Webhook-Secret" header on every call; we
# compare it (constant-time) to the WEBHOOK_SECRET env var. If the env var is unset the webhook runs
# OPEN — fine for local dev, but ALWAYS set it on any public/deployed instance.
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET")
if not WEBHOOK_SECRET:
    print("WARNING: WEBHOOK_SECRET not set — /webhook is UNAUTHENTICATED (local dev only).")


@app.get("/health")
def health():
    # Open, no auth — used by uptime / platform health checks.
    return {"status": "ok"}


@app.post("/webhook")
async def webhook(request: Request):
    # Reject anyone who doesn't present the shared secret (when one is configured).
    if WEBHOOK_SECRET:
        provided = request.headers.get("x-webhook-secret", "")
        if not hmac.compare_digest(provided, WEBHOOK_SECRET):
            return JSONResponse(status_code=401,
                                content={"status": "error", "message": "unauthorized"})

    body = await request.json()

    # Which practice is this call for? Identified by the number that was dialled.
    tenant = get_tenant(body.get("to_number"))
    if tenant is None:
        return {"status": "error",
                "message": f"unknown practice for number {body.get('to_number')}"}

    config, pms = tenant
    return dispatch(pms, body.get("function"), body.get("args") or {})


# Pinned to 8080 so we never collide with the AskMyDocs app on 8000.
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8080, reload=True)
