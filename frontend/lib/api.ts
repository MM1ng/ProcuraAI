import type { CartItem, ChatResponse, Order, PaymentStatus, Product, ProcurementHistoryRecord, ProcurementPlan, QuickOptimizationAction } from "./types";
import type { LanguageCode } from "./i18n";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";
console.log("[api] API_BASE resolved to:", API_BASE);
const LOCAL_API_FALLBACK = API_BASE.includes("localhost")
  ? API_BASE.replace("localhost", "127.0.0.1")
  : API_BASE.replace("127.0.0.1", "localhost");

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const ri: RequestInit = { ...init, headers: { "Content-Type": "application/json", ...(init?.headers || {}) }, cache: "no-store" };
  let resp: Response;
  try { resp = await fetch(`${API_BASE}${path}`, ri); }
  catch (err) { if (LOCAL_API_FALLBACK === API_BASE) throw err; resp = await fetch(`${LOCAL_API_FALLBACK}${path}`, ri); }
  if (!resp.ok) {
    let detail = `${resp.status} ${resp.statusText}`;
    try { const b = await resp.json(); if (b?.detail) detail = String(b.detail); } catch {}
    throw new Error(detail);
  }
  return resp.json() as Promise<T>;
}

export const api = {
  chat(message: string, sessionId = "demo-session-001", language: LanguageCode = "en") {
    console.log("[api] Chat API URL:", `${API_BASE}/api/chat`);
    console.log("[api] Chat request body:", { message, session_id: sessionId, language });
    return request<ChatResponse>("/api/chat", { method: "POST", body: JSON.stringify({ message, session_id: sessionId, language }) });
  },
  optimizePlan(payload: { action: QuickOptimizationAction; session_id: string; language: LanguageCode; parsed_intent: Record<string, unknown>; current_plan: ProcurementPlan; message?: string }) {
    return request<ChatResponse>("/api/chat/optimize", { method: "POST", body: JSON.stringify(payload) });
  },
  async exportExcel(plan: ProcurementPlan) {
    const resp = await fetch(`${API_BASE}/api/export/excel`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ plan }) });
    if (!resp.ok) throw new Error(`${resp.status} ${resp.statusText}`);
    return resp.blob();
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
  createOrderFromCart(items: CartItem[], userId = "demo-user") {
    const pis = items.map(i => ({ product_id: i.product_id, name: i.name, category: i.category, brand: i.brand, supplier: i.supplier, quantity: i.quantity, unit_price: i.price, subtotal: i.price * i.quantity, rating: i.rating, stock: i.stock, delivery_days: i.delivery_days }));
    const total = pis.reduce((s, i) => s + i.subtotal, 0);
    const plan = { items: pis, total_amount: total, budget_status: "no_budget_provided", inventory_status: "valid", constraint_satisfaction: "satisfied" };
    return request<Order>("/api/orders", { method: "POST", body: JSON.stringify({ user_id: userId, plan }) });
  },
  createOrder(plan: ProcurementPlan, userId = "demo-user") {
    return request<Order>("/api/orders", { method: "POST", body: JSON.stringify({ user_id: userId, plan }) });
  },
  orders() { return request<{ items: Order[]; total: number }>("/api/orders"); },
  getOrder(id: string) { return request<Order>(`/api/orders/${id}`); },
  checkout(order: Order, planId: string) {
    return request<{ checkout_url: string; session_id: string }>("/api/payments/stripe/checkout", { method: "POST", body: JSON.stringify({ order_id: order.order_id, plan_id: planId }) });
  },
  createCheckoutSession(orderId: string, amount: number) {
    return request<{ checkout_url: string; session_id: string; provider?: string; status?: string }>("/api/payments/create-checkout-session", { method: "POST", body: JSON.stringify({ order_id: orderId, amount }) });
  },
  mockPaymentSuccess(orderId: string) {
    return request<{ order_id: string; status: string; message: string; order?: Order }>("/api/payments/mock-success", { method: "POST", body: JSON.stringify({ order_id: orderId }) });
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
