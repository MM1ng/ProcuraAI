# Stripe Payment Design

The payment layer is implemented through `/api/payments/create-checkout-session`.
The endpoint accepts an order ID and amount, then returns a checkout URL,
session ID, provider, and status.

## Mock Mode

When `USE_MOCK_PAYMENT=true` or `STRIPE_SECRET_KEY` is missing, the service
returns a local success URL with a mock session ID. This is the default demo
path.

## Stripe Test Mode

When `USE_MOCK_PAYMENT=false` and a `sk_test_...` key is configured, the
service creates a Stripe Checkout Session with one line item for the
procurement order. Use Stripe test card `4242 4242 4242 4242`.

The webhook endpoint is present and mock-safe. It can be extended to verify
Stripe signatures and update order status.
