# AI Shopping Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reposition the app as an AI Shopping Agent while fixing product/brand/category search intent handling, context reuse, permissions, i18n, and the consumer/admin UI split.

**Architecture:** Keep the existing FastAPI + Next.js + Ant Design architecture. Add first-class shopping/search intent metadata in the backend, return structured product-search results for search intents, and let the frontend render those results as product cards while admin-only screens keep technical evidence.

**Tech Stack:** FastAPI, Pydantic, pytest, Next.js App Router, React, TypeScript, Ant Design, Recharts.

---

### Task 1: Backend Search Intent And Context Rules

**Files:**
- Modify: `backend/app/agent/intent_parser.py`
- Modify: `backend/app/agent/procurement_agent.py`
- Modify: `backend/app/rag/retriever.py`
- Modify: `backend/app/services/product_service.py`
- Modify: `backend/app/api/products.py`
- Modify: `backend/app/agent/prompts.py`
- Test: `backend/tests/test_intent_parser.py`
- Test: `backend/tests/test_chat_followups.py`
- Test: `backend/tests/test_product_search.py`

- [ ] Add failing parser tests for `brand_search`, `category_search`, and explicit `refine_recommendation` reuse only.
- [ ] Add failing chat test proving a Dell brand query after a recommendation does not reuse previous budget/categories.
- [ ] Add failing product-search test proving brand filtering is exact and case-insensitive.
- [ ] Implement brand alias normalization and a top-level `intent` field while preserving `revision_intent` for existing plan code.
- [ ] Only merge previous intent/plan when the current message is an explicit refinement.
- [ ] Pass `brand`, `max_price`, category, rating, stock, and delivery constraints through retrieval and products API.
- [ ] For product/brand/category search intents, return an empty plan plus structured `retrieved_products` and a localized product-list answer instead of generating a recommendation plan.

### Task 2: Frontend Structured Product Results And Locale

**Files:**
- Modify: `frontend/lib/types.ts`
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/lib/i18n.tsx`
- Modify: `frontend/components/ChatPanel.tsx`
- Modify: `frontend/components/ProcurementPlanCard.tsx`
- Modify: `frontend/components/ProductTable.tsx`
- Modify: `frontend/styles/globals.css`

- [ ] Ensure every chat request carries the current `language` and no stale parsed intent/plan payload for new messages.
- [ ] Render `brand_search`, `product_search`, and `category_search` results as shopping product cards with localized labels.
- [ ] Make the consumer side panel business-only: requirement summary, rationale, budget, delivery, and stock status.
- [ ] Keep Raw JSON, Trace ID, Product vector Top-K, filters, policies, merchant evidence, and tool details admin-only.
- [ ] Localize chat prompts, empty states, statuses, buttons, product fields, history labels, and plan comparison labels.

### Task 3: Consumer/Admin Navigation, Auth, And UI Polish

**Files:**
- Modify: `frontend/components/AppShell.tsx`
- Modify: `frontend/app/login/page.tsx`
- Modify: `frontend/app/page.tsx`
- Modify: `frontend/app/products/page.tsx`
- Modify: `frontend/app/procurement/page.tsx`
- Modify: `frontend/app/orders/page.tsx`
- Modify: `frontend/app/history/page.tsx`
- Modify: `frontend/app/admin/page.tsx`
- Modify: `frontend/app/admin/observability/page.tsx`
- Modify: `frontend/app/admin/evaluation/page.tsx`
- Modify: `frontend/app/admin/traces/page.tsx`
- Modify: `frontend/app/admin/rag-evidence/page.tsx`
- Modify: `frontend/styles/globals.css`

- [ ] Rename visible product to `AI Shopping Agent` / `电商智能购物助手`.
- [ ] Consumer sidebar shows only AI Chat, Products, Recommendations, Orders, History.
- [ ] Admin sidebar shows Dashboard, Observability, Evaluation, Traces, Retrieval Evidence, Consumer Preview, Logout.
- [ ] Preserve user/admin credentials, localStorage login persistence, redirects, role badge, and logout behavior.
- [ ] Upgrade pages to modern e-commerce SaaS cards, badges, spacing, loading/empty states, and responsive columns.

### Task 4: Documentation, Verification, And Known Tooling

**Files:**
- Modify: `README.md`
- Modify: `backend/README.md`
- Modify: `frontend/README.md`
- Modify: `frontend/app/layout.tsx`
- Modify: `backend/main.py`
- Modify: `backend/app/__init__.py`

- [ ] Replace visible Enterprise Procurement Agent naming with AI Shopping Agent wording.
- [ ] Keep internal filenames/API compatibility where renaming would be too risky for the current scope.
- [ ] Run focused backend tests for parser, product search, chat language, and follow-ups.
- [ ] Run full backend pytest if time allows.
- [ ] Run `npm run build`.
- [ ] Run `npm run lint` and report current Next.js 16 lint tooling behavior if it fails historically.
