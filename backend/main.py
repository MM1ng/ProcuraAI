from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import chat, evaluation, llm, observability, orders, payments, products
from app.core.logging import configure_logging


configure_logging()

app = FastAPI(
    title="Enterprise Procurement Agent API",
    version="0.1.0",
    description="Agentic RAG procurement assistant with mock-safe payment, observability and evaluation.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(products.router)
app.include_router(chat.router)
app.include_router(llm.router)
app.include_router(orders.router)
app.include_router(payments.router)
app.include_router(observability.router)
app.include_router(evaluation.router)


@app.on_event("startup")
def startup() -> None:
    try:
        from app.core.database import create_tables

        create_tables()
    except Exception:
        # CSV/JSON fallback keeps the demo usable even if the DB is not ready.
        pass


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "enterprise-procurement-agent"}
