# Procurement History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a minimal Procurement History feature that saves, lists, restores, and deletes procurement plans without changing v1.0 procurement logic.

**Architecture:** Add an independent FastAPI router at `/api/history` backed by a lightweight JSON file under `data/`. The frontend calls the new API from the existing chat page and restores records by rehydrating current chat result state plus `localStorage.currentPlan`.

**Tech Stack:** FastAPI, Pydantic, local JSON storage, Next.js, React, Ant Design, pytest.

---

### Task 1: Backend History Service and API

**Files:**
- Create: `backend/app/services/history_service.py`
- Create: `backend/app/api/history.py`
- Modify: `backend/main.py`
- Test: `backend/tests/test_history_api.py`

- [ ] Write failing tests for create/list/detail/delete and 404 responses.
- [ ] Implement JSON file helpers with injectable file paths for tests.
- [ ] Implement `/api/history` routes without touching `/api/chat` or order/payment APIs.
- [ ] Run `pytest backend/tests/test_history_api.py -q`.

### Task 2: Frontend History MVP

**Files:**
- Modify: `frontend/lib/types.ts`
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/components/ChatPanel.tsx`

- [ ] Add `ProcurementHistoryRecord` and API client methods.
- [ ] Add a minimal History card in ChatPanel.
- [ ] Save the current result on demand.
- [ ] Restore a selected record into chat state and `currentPlan`.
- [ ] Delete a selected record and refresh the list.

### Task 3: Verification

**Commands:**
- `pytest -q`
- `npm run lint`
- `npm run build`
- `git status --short`

Confirm no runtime logs, cache files, or local temporary files are included in the final diff.
