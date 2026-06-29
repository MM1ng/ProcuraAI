# Stripe AI Tooling

ProcuraAI uses Stripe Checkout as the official production payment path. The
application creates a Checkout Session on the backend, redirects the user to
Stripe test mode Checkout, and relies on signed Stripe webhooks to update the
local order payment status.

Stripe AI tooling, MCP, and Skills were used in this project as development and
testing accelerators for the Stripe Checkout, webhook, and payment validation
logic. They are not used to let an LLM charge a customer directly.

## Controlled Payment Tool

ProcuraAI wraps payment creation as a controlled AI tool:

```python
create_checkout_for_selected_plan(plan_id: str, order_id: str)
```

The tool only requests creation of a Stripe Checkout Session. It delegates to
the existing backend payment service and does not call the Stripe API directly.
This keeps the payment action behind application guardrails instead of exposing
raw payment operations to an agent or model.

## Backend Guardrails

Before any Checkout Session is created, the backend reloads the order and the
selected procurement plan from server-side state. The backend must validate:

- the plan exists and matches the requested `plan_id`
- the plan is selectable
- the plan is not over budget
- the plan status is payable
- the order exists
- the order status is payable

Plans with `over_budget=true` or `selectable=false` are rejected and cannot
create a Checkout Session. Frontend-provided amounts are never trusted; Stripe
line items and totals are recalculated from backend plan items.

## Demo Mode

All course demos use Stripe test mode. The expected demo flow is:

1. Generate a budget-safe procurement plan.
2. Create an order from the selected plan.
3. Use the controlled Stripe AI tool or payment API to create a Checkout
   Session.
4. Pay in Stripe Checkout with a Stripe test card.
5. Let the signed webhook update the order status to `paid`.

The success page is only a user-facing confirmation page. The authoritative
payment state comes from the webhook.
