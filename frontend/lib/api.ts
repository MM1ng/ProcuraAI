import type { CartItem, ChatResponse, Order, PaymentStatus, Product, ProcurementHistoryRecord, ProcurementPlan, QuickOptimizationAction } from "./types";
import type { LanguageCode } from "./i18n";

const API_BASE = "http://127.0.0.1:8000";
type CallerContext = { csrf_token: string; expires_at: number; mode: string };

async function request<T>(path: string, init?: RequestInit, format: "json" | "blob" = "json"): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Content-Type", "application/json");
  if (init?.method && !["GET", "HEAD"].includes(init.method) && !["/api/caller/init", "/api/caller/clear-invalid"].includes(path)) {
    const caller = await request<CallerContext>("/api/caller/context");
    headers.set("X-CSRF-Token", caller.csrf_token);
  }
  const ri: RequestInit = { ...init, headers, credentials: "include", cache: "no-store" };
  const resp = await fetch(`${API_BASE}${path}`, ri);
  if (!resp.ok) {
    let detail = `${resp.status} ${resp.statusText}`;
    try {
      const b = await resp.json();
      if (typeof window !== "undefined" && ["CALLER_REQUIRED", "CALLER_INVALID_OR_EXPIRED", "CALLER_INVALID", "RESOURCE_NOT_OWNED", "ANONYMOUS_MODE_UNAVAILABLE"].includes(b?.detail?.code)) {
        window.dispatchEvent(new Event("procuraai-caller-unavailable"));
      }
      if (typeof b?.detail === "string") detail = b.detail;
      else if (b?.detail?.message) detail = String(b.detail.message);
      else if (["PLAN_SNAPSHOT_INVALID", "PLAN_CONFIRMATION_REQUIRED"].includes(b?.detail?.code)) detail = "Please display the current plan and confirm it again.";
      else if (b?.detail) detail = JSON.stringify(b.detail);
    } catch {}
    throw new Error(detail);
  }
  return (format === "blob" ? resp.blob() : resp.json()) as Promise<T>;
}

export const api = {
  callerContext() { return request<CallerContext>("/api/caller/context"); },
  async clearInvalidCaller() {
    const result = await request<{ cleared: boolean }>("/api/caller/clear-invalid", {
      method: "POST", headers: { "X-Anonymous-Reset": "clear-invalid-context" },
    });
    if (typeof window !== "undefined") window.dispatchEvent(new Event("procuraai-caller-unavailable"));
    return result;
  },
  async initializeCaller() {
    // Only an explicit user action calls this initializer. Invalid credentials
    // cannot silently mint a replacement actor; the server rejects that case.
    let headers: Record<string, string> = {};
    try { const current = await api.callerContext(); headers = { "X-CSRF-Token": current.csrf_token }; } catch {}
    return request<CallerContext>("/api/caller/init", { method: "POST", headers });
  },
  createChatSession() { return request<{ session_id: string }>("/api/chat/session", { method: "POST" }); },
  existingChatSession(sessionId: string) { return request<{ session_id: string }>(`/api/chat/session/${encodeURIComponent(sessionId)}`); },
  async recoverPaymentReturn(params: { order_id?: string; session_id?: string; mock?: boolean }) {
    await api.callerContext();
    if (params.order_id || params.session_id) {
      const query = new URLSearchParams();
      if (params.order_id) query.set("order_id", params.order_id);
      if (params.session_id) query.set("session_id", params.session_id);
      return request<Order>(`/api/payments/return-status?${query}`);
    }
    throw new Error("Payment outcome is unavailable: no existing order reference.");
  },
  async chat(message: string, sessionId: string, language: LanguageCode = "en", plan?: ProcurementPlan) {
    console.log("[api] Chat API URL:", `${API_BASE}/api/chat`);
    console.log("[api] Chat request body:", { message, session_id: sessionId, language });
    const binding = plan ? { plan_id: plan.plan_id, plan_hash: plan.plan_hash, plan_version: plan.plan_version } : {};
    // The server only consumes confirmation on an explicit transaction command.
    // Ordinary messages do not mint confirmations or mutate selection.
    return request<ChatResponse>("/api/chat", { method: "POST", body: JSON.stringify({ message, session_id: sessionId, language, ...binding }) });
  },
  optimizePlan(payload: { action: QuickOptimizationAction; session_id: string; language: LanguageCode; parsed_intent: Record<string, unknown>; current_plan: ProcurementPlan; message?: string }) {
    return request<ChatResponse>("/api/chat/optimize", { method: "POST", body: JSON.stringify(payload) });
  },
  async exportExcel(plan: ProcurementPlan) {
    return request<Blob>("/api/export/excel", { method: "POST", body: JSON.stringify({ plan }) }, "blob");
  },
  exportHistoryExcel(historyId: string) {
    return request<Blob>("/api/export/excel", { method: "POST", body: JSON.stringify({ history_id: historyId }) }, "blob");
  },
  history() { return request<{ items: ProcurementHistoryRecord[]; total: number }>("/api/history"); },
  historyDetail(id: string) { return request<ProcurementHistoryRecord>(`/api/history/${id}`); },
  saveHistory(p: { original_request: string; parsed_intent: Record<string, unknown>; procurement_plan: ProcurementPlan; trace: Record<string, unknown>; reasoning_summary?: string; messages?: Array<Record<string, unknown>>; order_draft?: Record<string, unknown> | null }) {
    return request<ProcurementHistoryRecord>("/api/history", { method: "POST", body: JSON.stringify(p) });
  },
  deleteHistory(id: string) { return request<{ deleted: boolean; id: string }>(`/api/history/${id}`, { method: "DELETE" }); },
  products(params: Record<string, string | number | undefined> = {}) {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== "") q.set(k, String(v)); });
    return request<{ items: Product[]; total: number }>(`/api/products?${q.toString()}`);
  },
  getProduct(id: string) { return request<Product>(`/api/products/${id}`); },
  quoteCart(items: CartItem[]) {
    const plan = { items: items.map(i => ({ product_id: i.product_id, quantity: i.quantity })) };
    return request<{ cart_token: string; plan: ProcurementPlan }>("/api/orders/cart/quote", { method: "POST", body: JSON.stringify({ plan }) });
  },
  createOrderFromCart(cartToken: string) {
    return request<Order>("/api/orders/cart", { method: "POST", body: JSON.stringify({ cart_token: cartToken }) });
  },
  confirmPlan(plan: ProcurementPlan, sessionId: string) {
    return request<{ confirmation_id: string }>("/api/chat/confirm", { method: "POST", body: JSON.stringify({ session_id: sessionId, plan_id: plan.plan_id, plan_hash: plan.plan_hash, plan_version: plan.plan_version }) });
  },
  selectPlan(plan: ProcurementPlan, sessionId: string, selected: ProcurementPlan) {
    return request<{ recommended_plan: ProcurementPlan; plan_options: ChatResponse["plan_options"]; selected_plan_id: string }>("/api/chat/select", { method: "POST", body: JSON.stringify({ session_id: sessionId, plan_id: plan.plan_id, plan_hash: plan.plan_hash, plan_version: plan.plan_version, selected_plan_id: selected.plan_id, selected_plan_hash: selected.plan_hash, selected_plan_version: selected.plan_version }) });
  },
  async createOrder(plan: ProcurementPlan, context: { sessionId: string }) {
    const confirmed = await api.confirmPlan(plan, context.sessionId);
    const selection = {
      plan_id: plan.plan_id,
      plan_option_id: plan.plan_option_id,
      budget: plan.budget,
      over_budget: plan.over_budget,
      budget_status: plan.budget_status,
      inventory_status: plan.inventory_status,
      constraint_satisfaction: plan.constraint_satisfaction,
      missing_categories: plan.missing_categories,
      constraints_relaxed: plan.constraints_relaxed,
      selectable: plan.selectable,
      items: plan.items.map(i => ({ product_id: i.product_id, quantity: i.quantity })),
    };
    return request<Order>("/api/orders", { method: "POST", body: JSON.stringify({ plan: selection, session_id: context.sessionId, plan_id: plan.plan_id, plan_hash: plan.plan_hash, plan_version: plan.plan_version, confirmation_id: confirmed.confirmation_id }) });
  },
  orders() { return request<{ items: Order[]; total: number }>("/api/orders"); },
  getOrder(id: string) { return request<Order>(`/api/orders/${id}`); },
  checkout(order: Order, _planId?: string) {
    return request<{ checkout_url: string; session_id: string }>("/api/payments/stripe/checkout", { method: "POST", body: JSON.stringify({ order_id: order.order_id }) });
  },
  createCheckoutSession(orderId: string) {
    return request<{ checkout_url: string; session_id: string; provider?: string; status?: string }>("/api/payments/stripe/checkout", { method: "POST", body: JSON.stringify({ order_id: orderId }) });
  },
  mockPaymentSuccess(orderId: string, sessionId: string) {
    return request<{ order_id: string; status: string; message: string; order?: Order }>("/api/payments/mock-success", { method: "POST", body: JSON.stringify({ order_id: orderId, session_id: sessionId }) });
  },
  confirmPayment(params: { order_id?: string; session_id?: string }) {
    return request<{ order_id: string; status: string; message: string; order?: Order }>("/api/payments/confirm", { method: "POST", body: JSON.stringify(params) });
  },
  paymentStatus() { return request<PaymentStatus>("/api/payments/status"); },
  observabilitySummary() { return request<Record<string, unknown>>("/api/observability/summary"); },
  observabilityTraces() { return request<{ items: Record<string, unknown>[]; total: number }>("/api/observability/traces"); },
  evaluationSummary() { return request<Record<string, unknown>>("/api/evaluation/summary"); },
  runMockEvaluation() { return request<{ status: string; generated_rows: number }>("/api/evaluation/run-mock", { method: "POST" }); },
  runAgentEvaluation() { return request<{ status: string; generated_rows: number }>("/api/evaluation/run-agent", { method: "POST" }); },
};
