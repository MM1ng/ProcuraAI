# Project Overview

Enterprise Procurement Agent is an intelligent procurement assistant for
enterprise office equipment. It turns natural-language purchase requests into
auditable procurement plans by combining intent parsing, product retrieval,
business constraint checks, order creation, mock-safe Stripe checkout,
observability, and evaluation dashboards.

The system is designed for an NLP course project but uses an enterprise-style
structure. The backend is modular FastAPI code with agent, RAG, service,
observability, evaluation, and script layers. The frontend is a Next.js
dashboard with operational pages for AI Chat, Products, Procurement Plan,
Orders, Observability, and Evaluation.

The local demo does not require real API keys. When OpenAI, Stripe, Langfuse,
Ragas, or MLflow credentials are unavailable, deterministic mock paths keep the
main workflow runnable.
