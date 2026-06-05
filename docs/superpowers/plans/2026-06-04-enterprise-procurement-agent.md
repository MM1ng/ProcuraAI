# Enterprise Procurement Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a runnable full-stack Enterprise Procurement Agent with NLP-style intent parsing, hybrid product retrieval, procurement planning, order creation, mock-safe Stripe payment, observability, evaluation dashboards, seed data, tests, and documentation.

**Architecture:** The backend is a modular FastAPI app using SQLAlchemy, service classes, deterministic mock fallbacks, and optional integration adapters. The frontend is a Next.js App Router application with Ant Design layout and Recharts dashboards. Seed scripts and docs make the project reproducible for course demo use.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, Stripe SDK, LangChain/Chroma-compatible interfaces, Ragas/MLflow placeholders, Pytest, Next.js, TypeScript, Ant Design, Recharts.

---

### Task 1: Project Foundation

**Files:**
- Create: `README.md`
- Create: `.env.example`
- Create: `docker-compose.yml`
- Create: `backend/README.md`
- Create: `backend/requirements.txt`
- Create: `frontend/README.md`
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/next.config.js`

- [x] **Step 1: Create the requested directory tree**

Run: `New-Item -ItemType Directory -Force ...`
Expected: all backend, frontend, data, docs, and Superpowers folders exist.

- [ ] **Step 2: Add root and package metadata**

Write environment examples, startup commands, and local mock mode notes.

### Task 2: Backend Red Tests

**Files:**
- Create: `backend/tests/test_intent_parser.py`
- Create: `backend/tests/test_product_search.py`
- Create: `backend/tests/test_budget_rules.py`
- Create: `backend/tests/test_order_flow.py`

- [ ] **Step 1: Write intent parser tests**

Expected behavior: a request for 20 interns under $3000 with keyboard, mouse,
and headset returns the matching people count, budget, and categories.

- [ ] **Step 2: Write product search tests**

Expected behavior: search returns products matching category and constraints,
ordered by rating, delivery days, and price.

- [ ] **Step 3: Write budget tests**

Expected behavior: totals classify as `within_budget` or `over_budget`.

- [ ] **Step 4: Write order flow tests**

Expected behavior: creating an order stores items, subtotal, total, and
`pending_payment` status.

- [ ] **Step 5: Run tests to verify RED**

Run: `cd backend && pytest`
Expected: tests fail because implementation modules do not exist yet.

### Task 3: Backend Core Implementation

**Files:**
- Create: `backend/main.py`
- Create: `backend/app/core/config.py`
- Create: `backend/app/core/database.py`
- Create: `backend/app/core/logging.py`
- Create: `backend/app/models/*.py`
- Create: `backend/app/schemas/*.py`
- Create: `backend/app/services/*.py`
- Create: `backend/app/agent/*.py`
- Create: `backend/app/rag/*.py`
- Create: `backend/app/observability/*.py`
- Create: `backend/app/evaluation/*.py`
- Create: `backend/app/api/*.py`

- [ ] **Step 1: Implement settings, database, and SQLAlchemy models**

Use SQLite fallback and table definitions matching the requested database
schema.

- [ ] **Step 2: Implement parser, search, and procurement planning**

Use deterministic rules for mock mode. Keep the service interfaces compatible
with future LLM/RAG integrations.

- [ ] **Step 3: Implement order and payment services**

Create orders with items and return mock Stripe URLs unless real Stripe test
credentials are configured.

- [ ] **Step 4: Implement observability and evaluation services**

Persist local logs and expose summary/traces/results endpoints.

- [ ] **Step 5: Wire FastAPI routers**

Expose all requested API endpoints including `/health`.

- [ ] **Step 6: Run tests to verify GREEN**

Run: `cd backend && pytest`
Expected: tests pass.

### Task 4: Data And Scripts

**Files:**
- Create: `data/evaluation_questions.csv`
- Create: `data/seed_notes.md`
- Create: `backend/app/scripts/generate_products.py`
- Create: `backend/app/scripts/seed_db.py`
- Create: `backend/app/scripts/ingest_products.py`
- Create: `backend/app/scripts/run_mock_evaluation.py`

- [ ] **Step 1: Generate product data**

Run: `cd backend && python -m app.scripts.generate_products`
Expected: `../data/products.csv` contains at least 300 products.

- [ ] **Step 2: Seed the local database**

Run: `cd backend && python -m app.scripts.seed_db`
Expected: SQLite database contains products and a demo user.

- [ ] **Step 3: Build local retrieval index**

Run: `cd backend && python -m app.scripts.ingest_products`
Expected: local JSON retrieval index is written.

- [ ] **Step 4: Generate mock evaluation logs**

Run: `cd backend && python -m app.scripts.run_mock_evaluation`
Expected: evaluation rows are available for the dashboard.

### Task 5: Frontend Implementation

**Files:**
- Create: `frontend/app/layout.tsx`
- Create: `frontend/app/page.tsx`
- Create: `frontend/app/*/page.tsx`
- Create: `frontend/components/*.tsx`
- Create: `frontend/lib/*.ts`
- Create: `frontend/styles/globals.css`

- [ ] **Step 1: Implement application shell**

Use Ant Design `Layout`, navigation menu, and a compact enterprise style.

- [ ] **Step 2: Implement workflow pages**

Build chat, products, procurement, orders, payment success/cancel,
observability, and evaluation pages.

- [ ] **Step 3: Implement API client and types**

Keep backend DTO names aligned with Pydantic schemas.

### Task 6: Course Documentation

**Files:**
- Create: `docs/01_project_overview.md`
- Create: `docs/02_requirements.md`
- Create: `docs/03_architecture.md`
- Create: `docs/04_rag_agent_design.md`
- Create: `docs/05_database_design.md`
- Create: `docs/06_evaluation_metrics.md`
- Create: `docs/07_observability_design.md`
- Create: `docs/08_stripe_payment_design.md`
- Create: `docs/09_demo_script.md`
- Create: `docs/10_course_report_outline.md`

- [ ] **Step 1: Document requirements and architecture**

Write concise, presentation-ready English documentation.

- [ ] **Step 2: Document demo and reporting flow**

Include scriptable demo steps and course report outline.

### Task 7: Verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Run product generation**

Run: `cd backend && python -m app.scripts.generate_products`
Expected: 300+ products.

- [ ] **Step 2: Run backend tests**

Run: `cd backend && pytest`
Expected: all tests pass.

- [ ] **Step 3: Run API smoke checks if dependencies are available**

Run: `uvicorn main:app --port 8000`, then check `/health` and `/api/chat`.
Expected: healthy status and chat response containing parsed intent and plan.

- [ ] **Step 4: Record any local limitations**

If package installation or runtime checks cannot complete, add Known Issues in
the README with the exact command and reason.
