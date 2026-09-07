"""FastAPI application entrypoint."""
from __future__ import annotations

import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import (
    accounts,
    ai,
    analytics,
    auth,
    campaigns,
    companies,
    crm,
    health,
    imports,
    inbox,
    leads,
    linkedin,
    suppression,
    tracking,
    whatsapp,
)
from app.core.config import settings
from app.core.logging import configure_logging, request_id_ctx

configure_logging()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version="0.1.0",
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
)

# NOTE ON ORDER: middleware added later is the OUTER layer. We register the
# request-id/error-catching middleware FIRST (inner) and CORS LAST (outer), so
# that even 500 responses this middleware produces still get CORS headers —
# otherwise the browser sees an opaque network failure instead of the error body.
import logging

logger = logging.getLogger(__name__)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    rid = request.headers.get("X-Request-Id") or str(uuid.uuid4())
    token = request_id_ctx.set(rid)
    try:
        response = await call_next(request)
    except Exception:  # noqa: BLE001 — return JSON (inside CORS) instead of bubbling to ServerErrorMiddleware
        logger.exception("Unhandled error")
        response = JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "request_id": rid},
        )
    finally:
        request_id_ctx.reset(token)
    response.headers["X-Request-Id"] = rid
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Routes
app.include_router(health.router)
_p = settings.API_V1_PREFIX
app.include_router(auth.router, prefix=_p)
app.include_router(leads.router, prefix=_p)
app.include_router(companies.router, prefix=_p)
app.include_router(campaigns.router, prefix=_p)
app.include_router(crm.router, prefix=_p)
app.include_router(suppression.router, prefix=_p)
app.include_router(imports.router, prefix=_p)
app.include_router(accounts.router, prefix=_p)
app.include_router(inbox.router, prefix=_p)
app.include_router(linkedin.router, prefix=_p)
app.include_router(whatsapp.router, prefix=_p)
app.include_router(ai.router, prefix=_p)
app.include_router(analytics.router, prefix=_p)
# Public tracking endpoints (open pixel, click redirect, unsubscribe) live at the root
# so outbound-mail URLs stay short; the per-message tracking_id is the capability.
app.include_router(tracking.router)


@app.get("/")
def root() -> dict:
    return {"service": settings.PROJECT_NAME, "version": "0.1.0", "docs": "/docs"}
