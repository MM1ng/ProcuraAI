export type Product = {
  product_id: string;
  name: string;
  category: string;
  brand: string;
  price: number;
  rating: number;
  stock: number;
  supplier: string;
  delivery_days: number;
  warranty_months: number;
  compliance_level: string;
  description: string;
  tags: string;
};

export type PlanItem = {
  product_id: string;
  name: string;
  category: string;
  brand?: string;
  supplier?: string;
  quantity: number;
  unit_price: number;
  subtotal: number;
  rating?: number;
  stock?: number;
  delivery_days?: number;
  reason?: string;
  description?: string;
};

export type QuickOptimizationAction = "make_cheaper" | "improve_quality" | "faster_delivery" | "prefer_dell" | "regenerate";

export type ProcurementPlan = {
  items: PlanItem[];
  selected_items?: PlanItem[];
  total_amount: number;
  previous_total_amount?: number | null;
  savings_amount?: number | null;
  revision_type?: string;
  revision_note?: string;
  replacement_categories?: string[];
  budget?: number;
  budget_status: string;
  inventory_status: string;
  constraint_satisfaction: string;
  recommendation_reason?: string;
  recommendation_summary?: string;
  plan_option_id?: string;
  plan_strategy?: string;
};

export type PlanOption = {
  id: string;
  name: string;
  strategy: "cost_optimized" | "balanced" | "premium" | string;
  description: string;
  plan: ProcurementPlan;
};

export type RetrievalEvidence = {
  products?: Array<Record<string, unknown>>;
  policies?: Array<Record<string, unknown>>;
  suppliers?: Array<Record<string, unknown>>;
  constraints?: Record<string, unknown>;
  constraints_relaxed?: boolean;
  retrieval_mode?: string;
};

export type ChatResponse = {
  session_id: string;
  parsed_intent: Record<string, unknown>;
  recommended_plan: ProcurementPlan;
  plan_options: PlanOption[];
  selected_plan_id?: string | null;
  answer: string;
  trace_id: string;
  retrieved_products: Product[];
  retrieval_evidence?: RetrievalEvidence;
  model_provider: string;
  model_name: string;
  used_mock_llm: boolean;
  llm_error?: string | null;
  llm_timings?: Record<string, number | null | undefined>;
  used_previous_context: boolean;
  previous_trace_id?: string | null;
};

export type ProcurementHistoryRecord = {
  id: string;
  created_at: string;
  original_request: string;
  parsed_intent: Record<string, unknown>;
  agent_understanding?: Record<string, unknown>;
  selected_plan: ProcurementPlan;
  procurement_plan?: ProcurementPlan;
  total_cost: number;
  trace: Record<string, unknown>;
  reasoning_summary?: string;
  messages?: Array<Record<string, unknown>>;
  order_draft?: Record<string, unknown> | null;
};

export type PaymentStatus = {
  payment_provider: string;
  use_mock_payment: boolean;
  has_stripe_secret_key: boolean;
};

export type Order = {
  order_id: string;
  user_id: string;
  order_items: PlanItem[];
  total_amount: number;
  status: string;
  stripe_session_id?: string | null;
  created_at: string;
};
