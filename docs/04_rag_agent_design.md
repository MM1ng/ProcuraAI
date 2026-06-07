# RAG And Agent Design

## Product Context Construction

Each product is converted into a retrieval text that combines product name,
brand, category, supplier, description, tags, price, rating, stock, delivery
days, and compliance level. The local ingest script writes this context to the
ignored JSON fallback index at `data/retrieval_index.json` and to the local
Chroma `products` collection under `data/chroma/`.

Procurement policies and supplier profiles are loaded from:

- `data/procurement_policies.json`
- `data/suppliers.json`

They are ingested into separate Chroma collections named
`procurement_policies` and `suppliers`.

## Embeddings And Vector Store

The current vector path uses deterministic local hash embeddings with 384
dimensions and L2 normalization. This avoids external embedding API keys while
keeping tests stable and reproducible.

Chroma is used as the local vector database. If Chroma is unavailable, empty, or
throws during query, retrieval falls back to the local JSON/CSV search path.

## Hybrid Retrieval

Retrieval combines:

- Vector recall over product context.
- Category filtering from parsed and normalized intent.
- Structured constraints for price, rating, stock, and delivery days.
- Ranking by vector score, rating, delivery speed, and price.

If all vector-recalled products are removed by structured filters, the retriever
returns the best vector candidates with `constraints_relaxed=true` in retrieval
evidence so the UI can explain the relaxation.

`POST /api/chat` includes optional `retrieval_evidence`:

- `products`: product vector Top-K summary with score, reason, and matched fields
- `policies`: matching procurement policy snippets
- `suppliers`: matching supplier profile snippets
- `constraints`: structured filters applied during retrieval
- `constraints_relaxed`: whether no candidate survived strict filtering

## Dynamic Category Normalization

Before category filtering, the agent loads allowed categories from
`data/products.csv`. This keeps category normalization tied to the actual
catalog instead of a fixed code-only list.

The normalization order is:

1. Exact match against an allowed category.
2. Case-insensitive match against an allowed category.
3. Stable multilingual aliases for common procurement terms.
4. Conservative string similarity for close English variants.
5. Optional LLM category selection, constrained to the allowed categories.

When confidence is low, the original category is preserved and the parsed
intent includes a warning. This avoids silently mapping an unknown request to
the wrong catalog category.

Each parsed intent can include trace data:

- `original_category`
- `normalized_category`
- `normalization_method`
- `allowed_categories`
- `warning`

For example, the Chinese request category `显示器` normalizes to `Monitor`
before retrieval, so the structured category filter can match the Monitor rows
in the catalog.

## Agent Tools

The workflow includes tool-style functions:

- `parse_purchase_request`
- `search_products`
- `filter_products_by_constraints`
- `check_inventory`
- `calculate_budget`
- `generate_procurement_plan`
- `generate_plan_options`
- `create_order`
- `create_stripe_checkout`
- `log_observability_event`
- `evaluate_response_mock`

## qwen3.7-max LLM Strategy

The backend now uses `langchain_community.llms.tongyi.Tongyi` with
`settings.QWEN_MODEL` through `app.services.llm_service.safe_llm_invoke`.
`DASHSCOPE_API_KEY` is read from the environment and copied into
`os.environ["DASHSCOPE_API_KEY"]` before creating the Tongyi model.

qwen3.7-max is used for:

- Purchase intent extraction from natural language into structured JSON.
- Natural language recommendation explanation based only on retrieved products
  and the calculated procurement plan.
- Multi-turn procurement response generation through the agent response path,
  with provider metadata returned to the chat API.

Retrieval, inventory validation, budget calculation, and product selection stay
deterministic in code. qwen3.7-max is not allowed to invent products, prices,
stock, suppliers, delivery days, ratings, or discounts; it only explains data
already retrieved and calculated by the backend.

When `USE_MOCK_LLM=true`, or when `DASHSCOPE_API_KEY` is missing or Tongyi
raises an error, the service falls back to mock-safe output. Intent parsing then
uses the rule-based parser, and plan explanation uses the local template, so the
demo remains reproducible.

## Compare Plans

The v2 plan comparison layer is additive. The original calculated
`recommended_plan` remains available for backward compatibility, while the
agent also returns `plan_options`:

- `plan_a`: cost optimized
- `plan_b`: balanced
- `plan_c`: premium

Each option uses the same retrieved product set and the same parsed intent. The
strategy layer selects different eligible products per category, then reuses
the deterministic procurement plan calculation so totals, budget status,
inventory status, and constraint satisfaction are computed consistently.

`plan_b` is preferred by default when it is within budget. If it exceeds the
user's budget and another option is budget-safe, the backend selects the
lowest-cost within-budget option as the default `recommended_plan`. The
frontend selection only changes the currently displayed plan and downstream
actions; it does not mutate the catalog, retrieval results, or session parsing.
