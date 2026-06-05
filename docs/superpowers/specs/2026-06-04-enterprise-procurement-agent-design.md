# Enterprise Procurement Agent Design

## Context

The project starts from an empty course workspace and must produce a runnable,
presentation-ready NLP/RAG/Agent/Payment/Evaluation system. The pasted
requirements are treated as the approved product specification because the user
explicitly requested direct file creation and implementation.

## Product Scope

Enterprise Procurement Agent is an internal procurement assistant for office
equipment. A user describes a purchase request in natural language, the backend
parses constraints, retrieves and filters products, produces a procurement
plan, creates an order, and returns a Stripe test or mock checkout URL. The
frontend provides an enterprise admin experience with chat, product search,
procurement plans, orders, observability, and evaluation dashboards.

## Architecture

The application is split into a FastAPI backend and a Next.js TypeScript
frontend. The backend owns business logic, persistence, observability, and
mock-safe integrations. The frontend calls the backend over HTTP and renders
workflow pages with Ant Design and Recharts.

The backend uses SQLAlchemy models for products, users, orders,
observability logs, and evaluation logs. SQLite is the default local database;
PostgreSQL can be enabled with `DATABASE_URL`. RAG uses a Chroma-compatible
ingest/retrieval interface with a deterministic local fallback so the demo
works without external keys or services.

## Agent Workflow

1. Parse the purchase request into `people_count`, `budget`, `categories`,
   preferences, and hard constraints.
2. Search products with hybrid retrieval: text matching, category filtering,
   price/rating/stock/delivery filters, and deterministic ranking.
3. Generate a procurement plan with item quantities, totals, inventory status,
   budget status, constraint satisfaction, and rationale.
4. Log the trace locally and optionally forward Langfuse trace events when
   credentials exist.
5. Create an order from the selected plan.
6. Create a Stripe checkout session, or return a mock URL when mock payment is
   enabled or Stripe credentials are absent.

## Frontend Experience

The first screen is the application shell, not a marketing page. It has a left
navigation menu, a compact top title, and operational pages:

- AI Chat with chat history, parsed intent, procurement plan, create-order,
  and payment actions.
- Products with filters and searchable table.
- Procurement Plan with budget, inventory, and rationale views.
- Orders with status and detail display.
- Observability with metrics, trace table, and latency/tool charts.
- Evaluation with RAG, business, and system metrics.

## Mock And Integration Strategy

The system must run without API keys. Mock LLM, mock payment, local tracing,
and mock evaluation are first-class paths. Optional integrations are loaded
behind service adapters and guarded by settings:

- OpenAI/LangChain when `OPENAI_API_KEY` is set and mock mode is disabled.
- Stripe test checkout when `STRIPE_SECRET_KEY` is set and mock payment is
  disabled.
- Langfuse when public and secret keys are configured.
- MLflow/Ragas structures are included while local mock evaluation keeps the
  dashboard demonstrable.

## Testing Strategy

Core backend behavior is tested first:

- Intent parsing extracts people count, budget, categories, and constraints.
- Product search respects category, budget, rating, stock, and delivery filters.
- Budget rules classify within-budget and over-budget plans.
- Order flow persists an order with items and totals.

Frontend smoke quality is supported through TypeScript structure and reusable
API/types components, while runtime verification focuses on backend tests and
API smoke checks.

## Deliverables

- Complete requested directory structure under `enterprise-procurement-agent`.
- Seed data generator and `data/products.csv` with at least 300 products.
- FastAPI backend with requested endpoints.
- Next.js frontend pages and components.
- Root README, backend/frontend READMEs, and course docs.
- Superpowers spec and implementation plan.
- Backend tests and verification notes.
