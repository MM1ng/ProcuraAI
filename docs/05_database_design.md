# Database Design

## Tables

### products

Stores procurement catalog data: `product_id`, `name`, `category`, `brand`,
`price`, `rating`, `stock`, `supplier`, `delivery_days`, `warranty_months`,
`compliance_level`, `description`, and `tags`.

### users

Stores requester information: `user_id`, `name`, `department`, `role`, and
`purchase_limit`.

### orders

Stores order headers: `order_id`, `user_id`, `total_amount`, `status`,
`stripe_session_id`, and `created_at`.

### order_items

Stores order lines: `order_item_id`, `order_id`, `product_id`, `quantity`,
`unit_price`, and `subtotal`.

### observability_logs

Stores trace data: `trace_id`, `user_query`, `parsed_intent`,
`retrieved_products`, `final_answer`, `tool_calls`, `latency_ms`, `error`, and
`created_at`.

### evaluation_logs

Stores evaluation data: `question`, `answer`, `contexts`, RAG metrics,
business metrics, `latency_ms`, and `created_at`.

SQLite is the default local database. PostgreSQL can be enabled by setting
`DATABASE_URL`.
