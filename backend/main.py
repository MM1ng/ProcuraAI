from __future__ import annotations

import logging
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api import chat, evaluation, export, history, llm, observability, orders, payments, products
from app.core.logging import configure_logging

configure_logging()
logger = logging.getLogger("main")

ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app = FastAPI(
    title="Enterprise Procurement Agent API",
    version="0.1.0",
    description="Agentic RAG procurement assistant with mock-safe payment, observability and evaluation.",
)


# Diagnostic request logger (inner middleware - added FIRST)
# Starlette add_middleware uses insert(0, ...), so first-added is innermost.
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.monotonic()
    response = await call_next(request)
    elapsed_ms = (time.monotonic() - start) * 1000
    logger.info(
        "%s %s origin=%s -> %s (%.0fms)",
        request.method,
        request.url.path,
        request.headers.get("origin", "-"),
        response.status_code,
        elapsed_ms,
    )
    return response


# CORS - outermost middleware (added LAST so it wraps everything)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)
logger.info("CORS middleware configured: origins=%s", ALLOWED_ORIGINS)


# Routers
app.include_router(products.router)
app.include_router(chat.router)
app.include_router(llm.router)
app.include_router(orders.router)
app.include_router(payments.router)
app.include_router(observability.router)
app.include_router(evaluation.router)
app.include_router(history.router)
app.include_router(export.router)


@app.on_event("startup")
def startup() -> None:
    logger.info("Server starting - CORS origins: %s", ALLOWED_ORIGINS)
    try:
        from app.core.database import create_tables

        create_tables()
    except Exception:
        pass


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "enterprise-procurement-agent"}
