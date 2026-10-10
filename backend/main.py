from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from fastapi.responses import JSONResponse
from app.services import order_service
from app.services.transaction_lock import order_writer_lease, require_writer_lease
from app.services.caller_identity import CallerDenied, COOKIE_NAME, CURRENT_CALLER, check_host, check_write, resolve_credential
from app.api import caller

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api import chat, decision, evaluation, export, history, llm, observability, orders, payments, products
from app.core.logging import configure_logging

configure_logging()
logger = logging.getLogger("main")

ALLOWED_ORIGINS = ["http://127.0.0.1:3000"]

@asynccontextmanager
async def lifespan(application):
    with order_writer_lease(order_service.ORDERS_FILE):
        yield

app = FastAPI(
    lifespan=lifespan,
    title="Enterprise Procurement Agent API",
    version="0.1.0",
    description="Agentic RAG procurement assistant with mock-safe payment, observability and evaluation.",
)

@app.exception_handler(CallerDenied)
async def caller_denied(request, exc):
    return JSONResponse({"detail": {"code": exc.code, "message": "当前浏览器无法访问此资源。请检查匿名凭据是否有效；系统不会自动切换身份。"}},
                        status_code=exc.status, headers={"Cache-Control": "no-store"})

@app.middleware("http")
async def caller_boundary(request, call_next):
    path = request.url.path
    protected = (path == "/api/chat" or path.startswith("/api/chat/") or path == "/api/procurement/plan"
                 or path == "/api/orders" or path.startswith("/api/orders/")
                 or path == "/api/history" or path.startswith("/api/history/") or path.startswith("/api/export/")
                 or path in {"/api/payments/stripe/checkout", "/api/payments/create-checkout-session",
                             "/api/payments/confirm", "/api/payments/mock-success", "/api/payments/return-status"})
    context_token = None
    try:
        if protected:
            check_host(request)
            actor, record = resolve_credential(request.cookies.get(COOKIE_NAME))
            if request.method not in {"GET", "HEAD", "OPTIONS"}:
                check_write(request, record)
                require_writer_lease()
            context_token = CURRENT_CALLER.set(actor)
        response = await call_next(request)
        if protected or path.startswith("/api/caller/"):
            response.headers["Cache-Control"] = "no-store"
        return response
    except CallerDenied as exc:
        return await caller_denied(request, exc)
    finally:
        if context_token is not None:
            CURRENT_CALLER.reset(context_token)


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
app.include_router(caller.router)
app.include_router(chat.router)
app.include_router(llm.router)
app.include_router(orders.router)
app.include_router(payments.router)
app.include_router(observability.router)
app.include_router(decision.router)
app.include_router(evaluation.router)
app.include_router(history.router)
app.include_router(export.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "enterprise-procurement-agent"}
