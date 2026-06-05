# Architecture

## High-Level Components

- Next.js frontend: pages, Ant Design components, Recharts dashboards, API
  client.
- FastAPI backend: HTTP API, procurement agent, RAG retrieval, product/order
  services, payment service, observability, evaluation, and scripts.
- Data layer: generated CSV catalog, SQLite/PostgreSQL-ready SQLAlchemy models,
  JSON fallback logs, local retrieval index.
- Integration layer: optional Stripe, Langfuse, Ragas, MLflow, and LangChain
  extension points.

## Data Flow

1. The user submits a request from `/chat`.
2. `/api/chat` calls the procurement agent.
3. The agent parses intent, retrieves catalog candidates, generates a plan, and
   writes an observability trace.
4. The frontend displays parsed intent and plan.
5. The user creates an order through `/api/orders`.
6. The user starts checkout through `/api/payments/create-checkout-session`.
7. Dashboards read `/api/observability/summary` and `/api/evaluation/summary`.

## Reliability Strategy

Every external service has a local fallback. This keeps the presentation path
stable while preserving realistic integration boundaries for future extension.
