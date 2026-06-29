"use client";

import { App, Button, Card, Collapse, Descriptions, Input, List, Popconfirm, Space, Statistic, Tag, Typography } from "antd";
import { CreditCardOutlined, DeleteOutlined, DownloadOutlined, HistoryOutlined, LoadingOutlined, RedoOutlined, SaveOutlined, SendOutlined, ShoppingCartOutlined, ThunderboltOutlined } from "@ant-design/icons";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { currency } from "@/lib/format";
import { useLanguage } from "@/lib/i18n";
import type { CartItem, ChatResponse, Order, PaymentStatus, ProcurementHistoryRecord, QuickOptimizationAction, RetrievalEvidence, Product } from "@/lib/types";
import ChatMessage from "./ChatMessage";
import OrderSummary from "./OrderSummary";
import ProcurementPlanCard from "./ProcurementPlanCard";
import ProductResultCards from "./ProductResultCards";
import CartDrawer from "./CartDrawer";

type ChatLine = { role: "user" | "agent"; content: string; streaming?: boolean; retrievalEvidence?: RetrievalEvidence };
const STREAM_CHUNK = 3;
const STREAM_MS = 18;
const quickActions: Array<{ action: QuickOptimizationAction; label: string }> = [
  { action: "make_cheaper", label: "Make Cheaper" }, { action: "improve_quality", label: "Improve Quality" },
  { action: "faster_delivery", label: "Faster Delivery" }, { action: "prefer_dell", label: "Prefer Dell" },
  { action: "regenerate", label: "Re-generate" },
];

function RetrievalEvidencePanel({ evidence }: { evidence?: RetrievalEvidence }) {
  if (!evidence) return null;
  const prods = evidence.products || [];
  const has = prods.length || (evidence.policies || []).length || (evidence.suppliers || []).length;
  if (!has) return null;
  return (
    <Card title="Retrieval Evidence" size="small">
      <Space direction="vertical" size={10} style={{ width: "100%" }}>
        <Space wrap>
          <Tag color="blue">Mode: {evidence.retrieval_mode || "unknown"}</Tag>
          {evidence.constraints_relaxed ? <Tag color="orange">Constraints relaxed</Tag> : null}
        </Space>
        <Collapse size="small" items={[{ key: "products", label: `Product Top-K (${prods.length})`, children: prods.map((item, i) => <Typography.Text key={i}>{i + 1}. {String(item.name)} · {String(item.category)}</Typography.Text>) }]} />
      </Space>
    </Card>
  );
}

function isPlanSelectable(p?: { selectable?: boolean; budget_status?: string; over_budget?: boolean } | null) {
  if (!p) return false;
  if (p.selectable === false) return false;
  return p.budget_status !== "over_budget" && p.over_budget !== true;
}



export default function ChatPanel() {
  const { language, t } = useLanguage();
  const { message } = App.useApp();
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [chat, setChat] = useState<ChatLine[]>([]);
  const [result, setResult] = useState<ChatResponse | null>(null);
  const [order, setOrder] = useState<Order | null>(null);
  const [paymentStatus, setPaymentStatus] = useState<PaymentStatus | null>(null);
  const [hist, setHist] = useState<ProcurementHistoryRecord[]>([]);
  const [lastReq, setLastReq] = useState("");
  const [histLoading, setHistLoading] = useState(false);
  const [opt, setOpt] = useState<QuickOptimizationAction | null>(null);
  const [co, setCo] = useState<string | null>(null);
  function getBudgetSourceLabel() {
    const source = result?.parsed_intent?.["budget_source"];
    if (source === "explicit") return t("chat.budgetExplicit");
    if (source === "inherited") return t("chat.budgetInherited");
    return t("chat.budgetNone");
  }
  function budgetStatusLabel(p?: { budget_status?: string; budget?: number | null } | null): string {
    if (!p) return "";
    const bs = p.budget_status;
    if (bs === "no_budget_provided" || p.budget === undefined || p.budget === null) return t("plan.noBudget");
    if (bs === "within_budget") return t("plan.withinBudget");
    if (bs === "over_budget") return t("plan.overBudget");
    return bs;
  }
  const chatEnd = useRef<HTMLDivElement | null>(null);

  const [cart, setCart] = useState<CartItem[]>([]);
  const [cartOpen, setCartOpen] = useState(false);
  const [creating, setCreating] = useState(false);

  useEffect(() => { api.paymentStatus().then(setPaymentStatus).catch(() => setPaymentStatus(null)); refreshHist(); }, []);
  useEffect(() => { chatEnd.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [chat, loading]);

  function stream(content: string, retrievalEvidence?: RetrievalEvidence) {
    return new Promise<void>(resolve => {
      let i = 0;
      setChat(c => [...c, { role: "agent", content: "", streaming: true, retrievalEvidence }]);
      const t = window.setInterval(() => {
        i = Math.min(content.length, i + STREAM_CHUNK);
        const v = content.slice(0, i);
        setChat(c => { const n = [...c]; const l = n[n.length - 1]; if (l?.role === "agent") n[n.length - 1] = { ...l, content: v, streaming: i < content.length }; return n; });
        if (i >= content.length) { window.clearInterval(t); resolve(); }
      }, STREAM_MS);
    });
  }

  async function submit(msg = input) {
    if (!msg.trim()) return;
    setLoading(true);
    const um = msg.trim(); setInput(""); setLastReq(um);
    setChat(c => [...c, { role: "user", content: um }]);
    try {
      const r = await api.chat(um, "demo-session-001", language);
      setResult(r);
      localStorage.setItem("currentPlan", JSON.stringify(r.recommended_plan));
      await stream(r.answer, r.retrieval_evidence);
      if (r.checkout_url) {
        setTimeout(() => { window.location.href = r.checkout_url!; }, 1500);
      }
    } catch (e) { setInput(um); message.error(e instanceof Error ? e.message : t("chat.requestFailed")); }
    finally { setLoading(false); }
  }

  function pid(p?: { plan_option_id?: string; plan_id?: string } | null) { return p?.plan_option_id || p?.plan_id || ""; }

  async function createOrder(plan = result?.recommended_plan) {
    if (!plan) return null;
    if (!isPlanSelectable(plan)) { message.warning("Over-budget plans require approval."); return null; }
    setCreating(true);
    try { const o = await api.createOrder(plan); setOrder(o); message.success(t("chat.orderCreated", { orderId: o.order_id })); return o; }
    catch (e) { message.error(e instanceof Error ? e.message : "Failed"); return null; }
    finally { setCreating(false); }
  }

  async function optimize(a: QuickOptimizationAction) {
    if (!result?.recommended_plan) return;
    setOpt(a);
    try {
      const r = await api.optimizePlan({ action: a, session_id: result.session_id, language, parsed_intent: result.parsed_intent, current_plan: result.recommended_plan, message: lastReq });
      setResult(r); setOrder(null);
      localStorage.setItem("currentPlan", JSON.stringify(r.recommended_plan));
      await stream(r.answer, r.retrieval_evidence);
    } catch (e) { message.error(e instanceof Error ? e.message : t("chat.requestFailed")); }
    finally { setOpt(null); }
  }

  async function xlsx() {
    if (!result?.recommended_plan) return;
    try { const b = await api.exportExcel(result.recommended_plan); const u = window.URL.createObjectURL(b); const a = document.createElement("a"); a.href = u; a.download = "plan.xlsx"; a.click(); window.URL.revokeObjectURL(u); }
    catch (e) { message.error(e instanceof Error ? e.message : "Export failed"); }
  }

  async function ensureOrder(plan: NonNullable<ChatResponse["recommended_plan"]>) {
    if (order && order.plan_id === pid(plan)) return order;
    return createOrder(plan);
  }

  async function pay(o: Order, planId = pid(result?.recommended_plan)) {
    if (result?.recommended_plan && !isPlanSelectable(result.recommended_plan)) { message.warning("Over-budget."); return; }
    if (!planId) { message.error("Missing plan id."); return; }
    try { setCo(planId); const ch = await api.checkout(o, planId); window.location.href = ch.checkout_url; }
    catch (e) { message.error(e instanceof Error ? e.message : "Checkout failed"); }
    finally { setCo(null); }
  }

  async function payPlan(plan: NonNullable<ChatResponse["recommended_plan"]>) {
    if (!isPlanSelectable(plan)) { message.warning("Over-budget."); return; }
    const o = await ensureOrder(plan);
    if (!o) return;
    await pay(o, pid(plan));
  }

  async function refreshHist() { setHistLoading(true); try { setHist((await api.history()).items); } catch { setHist([]); } finally { setHistLoading(false); } }

  async function saveHist() {
    if (!result?.recommended_plan) return;
    try {
      const s = await api.saveHistory({ original_request: lastReq, parsed_intent: result.parsed_intent, procurement_plan: result.recommended_plan, trace: { trace_id: result.trace_id, model_provider: result.model_provider, model_name: result.model_name, used_mock_llm: result.used_mock_llm }, reasoning_summary: result.answer, messages: [{ role: "user", content: lastReq }, { role: "agent", content: result.answer }], order_draft: order });
      setHist(c => [s, ...c.filter(i => i.id !== s.id)]);
      message.success("History saved");
    } catch (e) { message.error(e instanceof Error ? e.message : "Failed"); }
  }

  async function restoreHist(id: string) {
    const r = await api.historyDetail(id);
    const tid = typeof r.trace?.trace_id === "string" ? r.trace.trace_id : r.id;
    const restored: ChatResponse = { session_id: "demo-session-001", parsed_intent: r.parsed_intent, recommended_plan: r.selected_plan || r.procurement_plan, plan_options: [], selected_plan_id: null, answer: r.reasoning_summary || "", trace_id: tid, retrieved_products: [], model_provider: typeof r.trace?.model_provider === "string" ? r.trace.model_provider : "history", model_name: typeof r.trace?.model_name === "string" ? r.trace.model_name : "restored", used_mock_llm: Boolean(r.trace?.used_mock_llm), used_previous_context: false, previous_trace_id: null };
    setResult(restored); setOrder((r.order_draft as Order | null) || null); setLastReq(r.original_request);
    setChat([{ role: "user", content: r.original_request || "" }, { role: "agent", content: r.reasoning_summary || "" }]);
    localStorage.setItem("currentPlan", JSON.stringify(restored.recommended_plan));
  }

  async function delHist(id: string) { await api.deleteHistory(id); setHist(c => c.filter(i => i.id !== id)); message.success("Deleted"); }

  function selPlan(oid: string) {
    if (!result?.plan_options?.length) return;
    const o = result.plan_options.find(x => x.id === oid);
    if (!o || !isPlanSelectable(o.plan)) { message.warning("Over budget."); return; }
    setResult({ ...result, recommended_plan: o.plan, selected_plan_id: o.id }); setOrder(null);
    localStorage.setItem("currentPlan", JSON.stringify(o.plan));
  }

  // Cart
  function addCart(item: CartItem) {
    setCart(p => { const ex = p.find(i => i.product_id === item.product_id); if (ex) return p.map(i => i.product_id === item.product_id ? { ...i, quantity: i.quantity + 1 } : i); return [...p, { ...item, quantity: 1 }]; });
    message.success(`Added ${item.name}`);
  }
  function addPlanCart(items: CartItem[]) {
    setCart(p => { const n = [...p]; for (const it of items) { const ex = n.find(i => i.product_id === it.product_id); if (ex) ex.quantity += it.quantity; else n.push({ ...it }); } return n; });
    message.success("Plan added to cart");
  }
  function buyNow(p: Product) { addCart({ product_id: p.product_id, name: p.name, brand: p.brand, category: p.category, price: p.price, quantity: 1, supplier: p.supplier, delivery_days: p.delivery_days, stock: p.stock, rating: p.rating }); setCartOpen(true); }
  function updQty(pid: string, q: number) { setCart(p => p.map(i => i.product_id === pid ? { ...i, quantity: q } : i)); }
  function rmCart(pid: string) { setCart(p => p.filter(i => i.product_id !== pid)); }
  async function onCartOrder(o: Order) { setOrder(o); setCartOpen(false); setChat(c => [...c, { role: "agent", content: `Order ${o.order_id} created. Total: ${currency(o.total_amount)}.` }]); }

  const cps = isPlanSelectable(result?.recommended_plan);
  const rt = result?.type;

  function renderStructured() {
    if (!result) return null;
    if (rt === "product_results" && result.products?.length) {
      return <ProductResultCards products={result.products as Product[]} onAddToCart={addCart} onBuyNow={buyNow} />;
    }
    if (rt === "recommendation_plan") {
      return <ProcurementPlanCard plan={result.recommendation_plan ?? result.recommended_plan} products={result.retrieved_products || []} onExportExcel={xlsx} onAddToCart={addPlanCart} onCreateOrder={() => createOrder()} onPayPlan={() => payPlan(result.recommended_plan)} creatingOrder={creating} payingPlan={Boolean(co)} />;
    }
    return null;
  }

  function vf(k: string) { const v = result?.parsed_intent?.[k]; if (Array.isArray(v)) return v.join(", "); if (k === "budget" && (v === undefined || v === null)) return t("plan.noBudget"); return v === undefined || v === null || v === "" ? "-" : String(v); }
  function pv(k: string) { const v = result?.parsed_intent?.[k]; if (k === "min_rating" && v) return `>= ${v}`; if (k === "max_delivery_days" && v) return `<= ${v} days`; return vf(k); }
  function sc(s: string) { if (s === "cost_optimized") return "green"; if (s === "premium") return "purple"; return "blue"; }

  return (
    <>
      <div className="two-column">
        <Space direction="vertical" size={16} style={{ width: "100%" }}>
          {result?.checkout_url && result?.type === "order" ? (
            <Card size="small" style={{borderColor: "#52c41a", backgroundColor: "#f6ffed"}}>
              <Space>
                <ShoppingCartOutlined style={{fontSize: 20, color: "#52c41a"}} />
                <div>
                  <div style={{fontWeight: 600}}>{t("chat.orderCreated", {orderId: result.order_id})}</div>
                  <div>{t("chat.redirectingToPayment")}</div>
                </div>
                <Button type="primary" icon={<CreditCardOutlined />}
                  onClick={() => window.location.href = result.checkout_url!}>
                  {t("chat.payNow")}
                </Button>
              </Space>
            </Card>
          ) : null}
          <Card title={t("chat.title")}>
            <Space direction="vertical" size={12} style={{ width: "100%" }}>
              <div className="chat-surface" aria-live="polite">
                {chat.length ? chat.map((item, i) => <ChatMessage key={`${item.role}-${i}`} role={item.role === "agent" ? "assistant" : "user"} content={item.content} streaming={item.streaming} retrievalEvidence={item.retrievalEvidence} />) : <div className="chat-empty">{t("chat.noMessages")}</div>}
                {loading && chat[chat.length - 1]?.role === "user" ? <div className="chat-row is-agent"><div className="chat-avatar"><LoadingOutlined /></div><div className="chat-bubble"><div className="typing-dots"><span /><span /><span /></div></div></div> : null}
                <div ref={chatEnd} />
              </div>
              {renderStructured()}
              <div className="composer">
                <Input.TextArea value={input} onChange={e => setInput(e.target.value)} onPressEnter={e => { if (!e.shiftKey) { e.preventDefault(); submit(); } }} autoSize={{ minRows: 2, maxRows: 5 }} disabled={loading} />
                <Button type="primary" shape="circle" icon={<SendOutlined />} loading={loading} disabled={loading || !input.trim()} onClick={() => submit()} />
              </div>
              <Space wrap>
                <Button icon={<ShoppingCartOutlined />} onClick={() => setCartOpen(true)}>Cart ({cart.length})</Button>
                <Button icon={<ShoppingCartOutlined />} disabled={!result || !cps} onClick={() => createOrder()}>{t("chat.createOrder")}</Button>
                <Button icon={<SaveOutlined />} disabled={!result || !lastReq} onClick={saveHist}>Save History</Button>
                <Button icon={<CreditCardOutlined />} disabled={!order || !cps} onClick={() => order && pay(order)}>{t("chat.payWithStripe")}</Button>
                {paymentStatus ? <Tag color={paymentStatus.payment_provider === "stripe" ? "green" : "blue"}>{t("chat.paymentMode")}: {paymentStatus.payment_provider}</Tag> : null}
              </Space>
            </Space>
          </Card>
          <OrderSummary order={order} onPay={cps ? pay : undefined} />
          <Card title={<Space><HistoryOutlined />History</Space>} extra={<Button size="small" onClick={refreshHist} loading={histLoading}>Refresh</Button>}>
            <List loading={histLoading} dataSource={hist} locale={{ emptyText: "No saved history." }} renderItem={item => (
              <List.Item actions={[<Button key="r" type="link" onClick={() => restoreHist(item.id)}>Restore</Button>, <Popconfirm key="d" title="Delete?" okText="Delete" okButtonProps={{ danger: true }} onConfirm={() => delHist(item.id)}><Button type="text" danger icon={<DeleteOutlined />} /></Popconfirm>]}>
                <List.Item.Meta title={item.original_request || item.id} description={`${new Date(item.created_at).toLocaleString()} · $${item.total_cost.toFixed(2)}`} />
              </List.Item>
            )} />
          </Card>
        </Space>

        <Space direction="vertical" size={16} style={{ width: "100%" }}>
          <Card title={t("chat.parsedIntent")}>
            {result ? <Space wrap style={{ marginBottom: 12 }}><Tag color={result.used_mock_llm ? "orange" : "green"}>{t("chat.modelStatus")}: {result.model_provider} / {result.model_name}</Tag><Tag color={result.used_previous_context ? "blue" : "default"}>{t("chat.previousContext")}: {result.used_previous_context ? t("chat.usingPreviousContext") : t("chat.newConversation")}</Tag><Tag>{t("chat.trace")}: {result.trace_id}</Tag>{result.llm_error ? <Tag color="red">{result.llm_error}</Tag> : null}</Space> : null}
            {result ? <Space direction="vertical" size={12} style={{ width: "100%" }}><Descriptions column={1} size="small" bordered><Descriptions.Item label="Team Size">{vf("people_count")}</Descriptions.Item><Descriptions.Item label="Categories">{vf("categories")}</Descriptions.Item><Descriptions.Item label="Budget">{vf("budget")}</Descriptions.Item><Descriptions.Item label="Budget Source">{getBudgetSourceLabel()}</Descriptions.Item><Descriptions.Item label="Rating">{pv("min_rating")}</Descriptions.Item><Descriptions.Item label="Delivery">{pv("max_delivery_days")}</Descriptions.Item><Descriptions.Item label="Intent">{vf("revision_intent")}</Descriptions.Item></Descriptions></Space> : <Typography.Text code>{"{}"}</Typography.Text>}
          </Card>
          <RetrievalEvidencePanel evidence={result?.retrieval_evidence} />
          {result?.plan_options?.length ? <Card title="Compare Plans"><Space direction="vertical" size={12} style={{ width: "100%" }}>{result.plan_options.map(o => { const s = isPlanSelectable(o.plan); const sel = result.selected_plan_id === o.id; return <Card key={o.id} size="small" type="inner" title={<Space wrap><Typography.Text strong>{o.name}</Typography.Text><Tag color={sc(o.strategy)}>{o.description}</Tag><Tag color={s && o.plan.budget !== undefined && o.plan.budget !== null ? "green" : (o.plan.budget === undefined || o.plan.budget === null) ? "blue" : "red"}>{budgetStatusLabel(o.plan)}</Tag></Space>} extra={<Space><Button type={sel ? "primary" : "default"} size="small" disabled={!s} onClick={() => selPlan(o.id)}>{sel ? "Selected" : s ? "Select" : "Over Budget"}</Button>{sel && s ? <Button type="primary" size="small" icon={<CreditCardOutlined />} loading={co === pid(o.plan)} onClick={() => payPlan(o.plan)}>Pay</Button> : null}</Space>}><Space size={18} wrap><Statistic title="Total" value={o.plan.total_amount} precision={2} prefix="$" />{!s && o.plan.budget !== undefined && o.plan.budget !== null ? <Statistic title="Over Budget" value={o.plan.budget_gap || 0} precision={2} prefix="+$" /> : null}<Statistic title="Items" value={o.plan.items.length} /><Statistic title="Avg Rating" value={o.plan.avg_rating ?? 0} precision={1} /></Space></Card>; })}</Space></Card> : null}
          {result?.recommended_plan ? <Card title="Quick Optimization" size="small"><Space wrap>{quickActions.map(a => <Button key={a.action} icon={a.action === "regenerate" ? <RedoOutlined /> : <ThunderboltOutlined />} loading={opt === a.action} disabled={Boolean(opt)} onClick={() => optimize(a.action)}>{a.label}</Button>)}<Button icon={<DownloadOutlined />} onClick={xlsx}>Export Excel</Button></Space></Card> : null}
          {rt !== "recommendation_plan" ? <ProcurementPlanCard plan={result?.recommended_plan} products={result?.retrieved_products || []} onExportExcel={xlsx} /> : null}
        </Space>
      </div>
      <CartDrawer open={cartOpen} items={cart} onClose={() => setCartOpen(false)} onUpdateQuantity={updQty} onRemoveItem={rmCart} onOrderCreated={onCartOrder} />
    </>
  );
}
