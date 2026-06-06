# RAG And Agent Design

## Product Context Construction

Each product is converted into a retrieval text that combines product name,
brand, category, supplier, description, tags, price, rating, stock, delivery
days, and compliance level. The local ingest script writes this context to
`data/retrieval_index.json`.

## Hybrid Retrieval

Retrieval combines:

- Text matching over product context.
- Category filtering from parsed and normalized intent.
- Structured constraints for price, rating, stock, and delivery days.
- Ranking by text score, rating, delivery speed, and price.

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
