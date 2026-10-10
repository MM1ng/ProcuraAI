const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

function harness(replies, contextError = null) {
  const calls = [];
  const allCalls = [];
  const module = { exports: {} };
  const code = ts.transpileModule(fs.readFileSync(path.join(__dirname, '../lib/api.ts'), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText;
  vm.runInNewContext(code, { module, exports: module.exports, process: { env: {} },
    console: { log() {} }, URLSearchParams, Headers,
    fetch: async (url, init) => {
      const call = { path: new URL(url).pathname, body: init.body ? JSON.parse(init.body) : undefined, init, url };
      allCalls.push(call);
      if (call.path === '/api/caller/context') {
        return { ok: !contextError, status: contextError ? 401 : 200, statusText: 'Unauthorized',
          json: async () => contextError ? { detail: { message: contextError } } : { csrf_token: 'bound-csrf', expires_at: 9999999999 } };
      }
      calls.push(call);
      const reply = replies.shift();
      if (reply.networkError) throw new Error('offline');
      return { ok: !reply.error, status: reply.error ? 409 : 200, statusText: 'Conflict',
        json: async () => reply.error ? { detail: reply.error } : reply,
        blob: async () => ({ fixture: 'xlsx' }) };
    },
  });
  return { api: module.exports.api, calls, allCalls };
}

const plan = { plan_id: 'server-plan-v2', plan_option_id: 'legacy-option',
  plan_hash: 'server-hash', plan_version: 2, total_amount: 20,
  items: [{ product_id: 'p1', quantity: 2, unit_price: 10, subtotal: 20 }] };

test('chat order uses server-issued confirmation and displayed id/hash/version', async () => {
  const { api, calls } = harness([{ confirmation_id: 'server-confirmation' }, { order_id: 'order-1' }]);
  await api.createOrder(plan, { sessionId: 'session-1' });
  assert.deepEqual(calls.map(c => c.path), ['/api/chat/confirm', '/api/orders']);
  assert.equal(calls[1].body.plan_id, plan.plan_id);
  assert.equal(calls[1].body.plan.plan_id, plan.plan_id);
  assert.equal(calls[1].body.plan_hash, plan.plan_hash);
  assert.equal(calls[1].body.plan_version, plan.plan_version);
  assert.equal(calls[1].body.confirmation_id, 'server-confirmation');
});

test('selection binds both displayed source and displayed target', async () => {
  const { api, calls } = harness([{}]);
  const target = { ...plan, plan_id: 'server-alternative', plan_hash: 'alternative-hash' };
  await api.selectPlan(plan, 'session-1', target);
  assert.equal(calls[0].path, '/api/chat/select');
  assert.equal(calls[0].body.plan_id, plan.plan_id);
  assert.equal(calls[0].body.selected_plan_id, target.plan_id);
  assert.equal(calls[0].body.selected_plan_hash, target.plan_hash);
  assert.equal(calls[0].body.selected_plan_version, target.plan_version);
});

test('cart quoting has no order side effect; subsequent confirmation uses cart token', async () => {
  const { api, calls } = harness([{ cart_token: 'server-cart-token', plan }, { order_id: 'cart-order' }]);
  const quote = await api.quoteCart([{ product_id: 'p1', quantity: 2, price: 0.01 }]);
  assert.deepEqual(calls.map(c => c.path), ['/api/orders/cart/quote']);
  assert.equal(calls[0].body.plan.items[0].price, undefined);
  await api.createOrderFromCart(quote.cart_token);
  assert.equal(calls[1].path, '/api/orders/cart');
  assert.equal(calls[1].body.cart_token, 'server-cart-token');
  assert.equal(calls[1].body.plan, undefined);
});

test('rejected confirmation tells user to reconfirm and never submits an order', async () => {
  const { api, calls } = harness([{ error: { code: 'PLAN_SNAPSHOT_INVALID',
    message: 'Display the current plan and confirm it again.' } }]);
  await assert.rejects(api.createOrder(plan, { sessionId: 'session-1' }), /confirm it again/);
  assert.deepEqual(calls.map(c => c.path), ['/api/chat/confirm']);
});

test('writes carry browser credentials and bound CSRF; client user IDs are absent', async () => {
  const { api, calls, allCalls } = harness([{ confirmation_id: 'issued' }, { order_id: 'one' }]);
  await api.createOrder(plan, { sessionId: 'server-session' });
  assert.ok(allCalls.every(c => c.init.credentials === 'include' && c.init.cache === 'no-store'));
  assert.ok(calls.every(c => c.init.headers.get('X-CSRF-Token') === 'bound-csrf'));
  assert.ok(calls.every(c => c.body.user_id === undefined));
  assert.ok(allCalls.every(c => c.url.startsWith('http://127.0.0.1:8000/')));
});

test('invalid actor on payment return only reads context; no init/order/checkout/replay', async () => {
  const { api, allCalls } = harness([], 'Credential expired; outcome unavailable');
  await assert.rejects(api.recoverPaymentReturn({ order_id: 'existing', mock: true }), /unavailable/);
  assert.deepEqual(allCalls.map(c => c.path), ['/api/caller/context']);
});

for (const mock of [false, true]) {
  for (const status of ['pending_payment', 'paid']) {
    test(`payment return is GET-only for mock=${mock}, saved status=${status}`, async () => {
      const { api, calls, allCalls } = harness([{ order_id: 'existing', status }]);
      const result = await api.recoverPaymentReturn({ order_id: 'existing', session_id: 'stored-checkout', mock });
      assert.equal(result.status, status);
      assert.deepEqual(calls.map(c => c.path), ['/api/payments/return-status']);
      assert.equal(allCalls[0].path, '/api/caller/context');
      assert.ok(allCalls.every(c => !c.init.method || c.init.method === 'GET'));
      assert.ok(calls[0].url.includes('order_id=existing'));
      assert.ok(calls[0].url.includes('session_id=stored-checkout'));
    });
  }
}

test('payment return without reference never claims success or creates resources', async () => {
  const { api, calls } = harness([]);
  await assert.rejects(api.recoverPaymentReturn({}), /no existing order reference/);
  assert.equal(calls.length, 0);
});

test('protected request network failure has no localhost fallback or retry', async () => {
  const { api, allCalls } = harness([{ networkError: true }]);
  await assert.rejects(api.orders(), /offline/);
  assert.equal(allCalls.length, 1);
  assert.equal(allCalls[0].url, 'http://127.0.0.1:8000/api/orders');
});

test('explicit invalid-cookie clearing neither initializes actor nor replays a transaction', async () => {
  const { api, allCalls } = harness([{ cleared: true }], 'expired');
  await api.clearInvalidCaller();
  assert.deepEqual(allCalls.map(c => c.path), ['/api/caller/clear-invalid']);
  assert.equal(allCalls[0].init.method, 'POST');
  assert.equal(allCalls[0].init.headers.get('X-Anonymous-Reset'), 'clear-invalid-context');
});

test('history export uses an owned server reference plus cookie and CSRF', async () => {
  const { api, allCalls, calls } = harness([{}]);
  await api.exportHistoryExcel('owned-history');
  assert.equal(calls[0].path, '/api/export/excel');
  assert.equal(calls[0].body.history_id, 'owned-history');
  assert.equal(calls[0].body.plan, undefined);
  assert.ok(allCalls.every(c => c.init.credentials === 'include'));
  assert.equal(calls[0].init.headers.get('X-CSRF-Token'), 'bound-csrf');
});

test('explicit mock action submits both owned order and existing checkout reference', async () => {
  const { api, calls } = harness([{ status: 'paid' }]);
  await api.mockPaymentSuccess('owned-order', 'mock_existing');
  assert.equal(calls[0].path, '/api/payments/mock-success');
  assert.equal(calls[0].body.order_id, 'owned-order');
  assert.equal(calls[0].body.session_id, 'mock_existing');
  assert.equal(calls[0].init.headers.get('X-CSRF-Token'), 'bound-csrf');
});

test('live plan export also uses the protected cookie and CSRF transport', async () => {
  const { api, calls } = harness([{}]);
  await api.exportExcel(plan);
  assert.equal(calls[0].path, '/api/export/excel');
  assert.equal(calls[0].init.credentials, 'include');
  assert.equal(calls[0].init.headers.get('X-CSRF-Token'), 'bound-csrf');
  assert.equal(calls[0].body.plan.plan_id, plan.plan_id);
});
