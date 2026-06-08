import type {
  ChatResponse,
  Order,
  PaymentStatus,
  Product,
  ProcurementHistoryRecord,
  ProcurementPlan,
  QuickOptimizationAction
} from "./types";
import type { LanguageCode } from "./i18n";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";
const LOCAL_API_FALLBACK =
  API_BASE.includes("localhost") ? API_BASE.replace("localhost", "127.0.0.1") : API_BASE.replace("127.0.0.1", "localhost");

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const requestInit: RequestInit = {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {})
    },
    cache: "no-store"
  };

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, requestInit);
  } catch (error) {
    if (LOCAL_API_FALLBACK === API_BASE) throw error;
    response = await fetch(`${LOCAL_API_FALLBACK}${path}`, requestInit);
  }

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body?.detail) detail = String(body.detail);
    } catch {
      // Keep the HTTP status text when the backend does not return JSON.
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

export const api = {
  chat(message: string, sessionId = "demo-session-001", language: LanguageCode = "en") {
    return request<ChatResponse>("/api/chat", {
      method: "POST",
      body: JSON.stringify({ message, session_id: sessionId, language })
    });
  },
  optimizePlan(payload: {
    action: QuickOptimizationAction;
    session_id: string;
    language: LanguageCode;
    parsed_intent: Record<string, unknown>;
    current_plan: ProcurementPlan;
    message?: string;
  }) {
    return request<ChatResponse>("/api/chat/optimize", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },
  async exportExcel(plan: ProcurementPlan) {
    const response = await fetch(`${API_BASE}/api/export/excel`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ plan })
    });
    if (!response.ok) {
      throw new Error(`${response.status} ${response.statusText}`);
    }
    return response.blob();
  },
  history() {
    return request<{ items: ProcurementHistoryRecord[]; total: number }>("/api/history");
  },
  historyDetail(historyId: string) {
    return request<ProcurementHistoryRecord>(`/api/history/${historyId}`);
  },
  saveHistory(payload: {
    original_request: string;
    parsed_intent: Record<string, unknown>;
    procurement_plan: ProcurementPlan;
    trace: Record<string, unknown>;
    reasoning_summary?: string;
    messages?: Array<Record<string, unknown>>;
    order_draft?: Record<string, unknown> | null;
  }) {
    return request<ProcurementHistoryRecord>("/api/history", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },
  deleteHistory(historyId: string) {
    return request<{ deleted: boolean; id: string }>(`/api/history/${historyId}`, {
      method: "DELETE"
    });
  },
  products(params: Record<string, string | number | undefined> = {}) {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== "") query.set(key, String(value));
    });
    return request<{ items: Product[]; total: number }>(`/api/products?${query.toString()}`);
  },
  createOrder(plan: ProcurementPlan, userId = "demo-user") {
    return request<Order>("/api/orders", {
      method: "POST",
      body: JSON.stringify({ user_id: userId, plan })
    });
  },
  orders() {
    return request<{ items: Order[]; total: number }>("/api/orders");
  },
  checkout(order: Order, planId: string) {
    return request<{ checkout_url: string; session_id: string }>(
      "/api/payments/stripe/checkout",
      {
        method: "POST",
        body: JSON.stringify({
          order_id: order.order_id,
          plan_id: planId
        })
      }
    );
  },
  paymentStatus() {
    return request<PaymentStatus>("/api/payments/status");
  },
  observabilitySummary() {
    return request<Record<string, unknown>>("/api/observability/summary");
  },
  observabilityTraces() {
    return request<{ items: Record<string, unknown>[]; total: number }>("/api/observability/traces");
  },
  evaluationSummary() {
    return request<Record<string, unknown>>("/api/evaluation/summary");
  },
  runMockEvaluation() {
    return request<{ status: string; generated_rows: number }>("/api/evaluation/run-mock", {
      method: "POST"
    });
  },
  runAgentEvaluation() {
    return request<{ status: string; generated_rows: number }>("/api/evaluation/run-agent", {
      method: "POST"
    });
  }
};
