"""FastAPI app — the front door the voice agent (Retell) calls.

One real endpoint: POST /webhook. It reads the Contract 2 envelope, finds which practice the call
is for (by the dialled number), and routes the function to the right handler. Plus GET /health for
a quick "is it up?" check.

Run locally:  uvicorn app:app --reload   (from the backend/ directory)
"""

import os
import sys

from fastapi import FastAPI, Request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tenants import get_tenant      # noqa: E402
from handlers import dispatch       # noqa: E402

app = FastAPI(title="Synkris Voice Agent — webhook")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/webhook")
async def webhook(request: Request):
    body = await request.json()

    # Which practice is this call for? Identified by the number that was dialled.
    tenant = get_tenant(body.get("to_number"))
    if tenant is None:
        return {"status": "error",
                "message": f"unknown practice for number {body.get('to_number')}"}

    config, pms = tenant
    return dispatch(pms, body.get("function"), body.get("args") or {})
