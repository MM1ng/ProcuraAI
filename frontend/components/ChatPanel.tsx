"use client";

import { App, Button, Card, Collapse, Descriptions, Input, List, Popconfirm, Space, Statistic, Tag, Typography } from "antd";
import {
  CreditCardOutlined,
  DeleteOutlined,
  DownloadOutlined,
  HistoryOutlined,
  LoadingOutlined,
  RedoOutlined,
  SaveOutlined,
  SendOutlined,
  ShoppingCartOutlined,
  ThunderboltOutlined
} from "@ant-design/icons";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useLanguage } from "@/lib/i18n";
import type {
  ChatResponse,
  Order,
  PaymentStatus,
  ProcurementHistoryRecord,
  QuickOptimizationAction,
  RetrievalEvidence
} from "@/lib/types";
import ChatMessage from "./ChatMessage";
import OrderSummary from "./OrderSummary";
import ProcurementPlanCard from "./ProcurementPlanCard";

type ChatLine = { role: "user" | "agent"; content: string; streaming?: boolean };

const STREAM_CHUNK_SIZE = 3;
const STREAM_INTERVAL_MS = 18;
const quickActions: Array<{ action: QuickOptimizationAction; label: string }> = [
  { action: "make_cheaper", label: "Make Cheaper" },
  { action: "improve_quality", label: "Improve Quality" },
  { action: "faster_delivery", label: "Faster Delivery" },
  { action: "prefer_dell", label: "Prefer Dell" },
  { action: "regenerate", label: "Re-generate" }
];

function evidenceText(value: unknown) {
  if (Array.isArray(value)) return value.join(", ");
  if (value === undefined || value === null || value === "") return "-";
  return String(value);
}

function evidenceScore(value: unknown) {
  const score = Number(value || 0);
  return Number.isFinite(score) ? score.toFixed(2) : "-";
}

function RetrievalEvidencePanel({ evidence }: { evidence?: RetrievalEvidence }) {
  if (!evidence) return null;
  const products = evidence.products || [];
  const policies = evidence.policies || [];
  const suppliers = evidence.suppliers || [];
  const constraints = evidence.constraints || {};
  const hasEvidence = products.length || policies.length || suppliers.length;
  if (!hasEvidence) return null;

  return (
    <Card title="Retrieval Evidence" size="small">
      <Space direction="vertical" size={10} style={{ width: "100%" }}>
        <Space wrap>
          <Tag color="blue">Mode: {evidence.retrieval_mode || "unknown"}</Tag>
          {evidence.constraints_relaxed ? <Tag color="orange">Constraints relaxed</Tag> : null}
          {Object.entries(constraints).map(([key, value]) => (
            value === undefined || value === null || value === "" ? null : (
              <Tag key={key}>
                {key}: {evidenceText(value)}
              </Tag>
            )
          ))}
        </Space>
        <Collapse
          size="small"
          items={[
            {
              key: "products",
              label: `Product vector Top-K (${products.length})`,
              children: (
                <Space direction="vertical" size={8} style={{ width: "100%" }}>
                  {products.map((item, index) => (
                    <Typography.Text key={`${item.product_id}-${index}`}>
                      {index + 1}. {evidenceText(item.name)} · {evidenceText(item.category)} · score{" "}
                      {evidenceScore(item.score)} · {evidenceText(item.reason)}
                    </Typography.Text>
                  ))}
                </Space>
              )
            },
            {
              key: "policies",
              label: `Procurement policies (${policies.length})`,
              children: (
                <Space direction="vertical" size={8} style={{ width: "100%" }}>
                  {policies.map((item, index) => (
                    <Typography.Text key={`${item.id}-${index}`}>
                      {evidenceText(item.title)} · score {evidenceScore(item.score)}
                    </Typography.Text>
                  ))}
                </Space>
              )
            },
            {
              key: "suppliers",
              label: `Supplier knowledge (${suppliers.length})`,
              children: (
                <Space direction="vertical" size={8} style={{ width: "100%" }}>
                  {suppliers.map((item, index) => (
                    <Typography.Text key={`${item.id}-${index}`}>
                      {evidenceText(item.supplier || item.title)} · risk {evidenceText(item.risk_level)} · score{" "}
                      {evidenceScore(item.score)}
                    </Typography.Text>
                  ))}
                </Space>
              )
            }
          ]}
        />
      </Space>
    </Card>
  );
}

export default function ChatPanel() {
  const { language, t } = useLanguage();
  const { message } = App.useApp();
  const examples = [t("chat.example1"), t("chat.example2"), t("chat.example3"), t("chat.example4")];
  const [input, setInput] = useState(t("chat.example1"));
  const [loading, setLoading] = useState(false);
  const [chat, setChat] = useState<ChatLine[]>([]);
  const [result, setResult] = useState<ChatResponse | null>(null);
  const [order, setOrder] = useState<Order | null>(null);
  const [paymentStatus, setPaymentStatus] = useState<PaymentStatus | null>(null);
  const [historyRecords, setHistoryRecords] = useState<ProcurementHistoryRecord[]>([]);
  const [lastRequest, setLastRequest] = useState("");
  const [historyLoading, setHistoryLoading] = useState(false);
  const [optimizing, setOptimizing] = useState<QuickOptimizationAction | null>(null);
  const chatEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    api.paymentStatus().then(setPaymentStatus).catch(() => setPaymentStatus(null));
    refreshHistory();
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [chat, loading]);

  function streamAgentAnswer(content: string) {
    return new Promise<void>((resolve) => {
      let index = 0;
      setChat((current) => [...current, { role: "agent", content: "", streaming: true }]);
      const timer = window.setInterval(() => {
        index = Math.min(content.length, index + STREAM_CHUNK_SIZE);
        const visibleContent = content.slice(0, index);
        setChat((current) => {
          const next = [...current];
          const last = next[next.length - 1];
          if (last?.role === "agent") {
            next[next.length - 1] = {
              ...last,
              content: visibleContent,
              streaming: index < content.length
            };
          }
          return next;
        });
        if (index >= content.length) {
          window.clearInterval(timer);
          resolve();
        }
      }, STREAM_INTERVAL_MS);
    });
  }

  async function submit(messageText = input) {
    if (!messageText.trim()) return;
    setLoading(true);
    const userMessage = messageText.trim();
    setInput("");
    setLastRequest(userMessage);
    setChat((current) => [...current, { role: "user", content: userMessage }]);
    try {
      const response = await api.chat(userMessage, "demo-session-001", language);
      setResult(response);
      localStorage.setItem("currentPlan", JSON.stringify(response.recommended_plan));
      await streamAgentAnswer(response.answer);
    } catch (error) {
      setInput(userMessage);
      message.error(error instanceof Error ? error.message : t("chat.requestFailed"));
    } finally {
      setLoading(false);
    }
  }

  async function createOrder() {
    if (!result?.recommended_plan) return;
    const created = await api.createOrder(result.recommended_plan);
    setOrder(created);
    message.success(t("chat.orderCreated", { orderId: created.order_id }));
  }

  async function optimize(action: QuickOptimizationAction) {
    if (!result?.recommended_plan) return;
    setOptimizing(action);
    try {
      const response = await api.optimizePlan({
        action,
        session_id: result.session_id,
        language,
        parsed_intent: result.parsed_intent,
        current_plan: result.recommended_plan,
        message: lastRequest
      });
      setResult(response);
      setOrder(null);
      localStorage.setItem("currentPlan", JSON.stringify(response.recommended_plan));
      await streamAgentAnswer(response.answer);
    } catch (error) {
      message.error(error instanceof Error ? error.message : t("chat.requestFailed"));
    } finally {
      setOptimizing(null);
    }
  }

  async function exportExcel() {
    if (!result?.recommended_plan) return;
    try {
      const blob = await api.exportExcel(result.recommended_plan);
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "procurement_plan.xlsx";
      anchor.click();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      message.error(error instanceof Error ? error.message : "Export failed");
    }
  }

  async function pay(targetOrder: Order) {
    const checkout = await api.checkout(targetOrder);
    window.location.href = checkout.checkout_url;
  }

  async function refreshHistory() {
    setHistoryLoading(true);
    try {
      const response = await api.history();
      setHistoryRecords(response.items);
    } catch {
      setHistoryRecords([]);
    } finally {
      setHistoryLoading(false);
    }
  }

  async function saveHistory() {
    if (!result?.recommended_plan) return;
    const saved = await api.saveHistory({
      original_request: lastRequest,
      parsed_intent: result.parsed_intent,
      procurement_plan: result.recommended_plan,
      trace: {
        trace_id: result.trace_id,
        model_provider: result.model_provider,
        model_name: result.model_name,
        used_mock_llm: result.used_mock_llm
      },
      reasoning_summary: result.answer,
      messages: [
        { role: "user", content: lastRequest },
        { role: "agent", content: result.answer }
      ],
      order_draft: order
    });
    setHistoryRecords((current) => [saved, ...current.filter((item) => item.id !== saved.id)]);
    message.success("History saved");
  }

  async function restoreHistory(historyId: string) {
    const record = await api.historyDetail(historyId);
    const traceId = typeof record.trace?.trace_id === "string" ? record.trace.trace_id : record.id;
    const restoredResult: ChatResponse = {
      session_id: "demo-session-001",
      parsed_intent: record.parsed_intent,
      recommended_plan: record.selected_plan || record.procurement_plan,
      plan_options: [],
      selected_plan_id: null,
      answer: record.reasoning_summary || "",
      trace_id: traceId,
      retrieved_products: [],
      model_provider: typeof record.trace?.model_provider === "string" ? record.trace.model_provider : "history",
      model_name: typeof record.trace?.model_name === "string" ? record.trace.model_name : "restored",
      used_mock_llm: Boolean(record.trace?.used_mock_llm),
      used_previous_context: false,
      previous_trace_id: null
    };
    setResult(restoredResult);
    setOrder((record.order_draft as Order | null) || null);
    setLastRequest(record.original_request);
    setChat([
      { role: "user", content: record.original_request || "Restored procurement request" },
      { role: "agent", content: record.reasoning_summary || "Restored procurement plan" }
    ]);
    localStorage.setItem("currentPlan", JSON.stringify(restoredResult.recommended_plan));
    message.success("History restored");
  }

  async function deleteHistory(historyId: string) {
    await api.deleteHistory(historyId);
    setHistoryRecords((current) => current.filter((item) => item.id !== historyId));
    message.success("History deleted");
  }

  function selectPlan(optionId: string) {
    if (!result?.plan_options?.length) return;
    const option = result.plan_options.find((item) => item.id === optionId);
    if (!option) return;
    const nextResult = {
      ...result,
      recommended_plan: option.plan,
      selected_plan_id: option.id
    };
    setResult(nextResult);
    setOrder(null);
    localStorage.setItem("currentPlan", JSON.stringify(option.plan));
    message.success(`${option.name} selected`);
  }

  function strategyColor(strategy: string) {
    if (strategy === "cost_optimized") return "green";
    if (strategy === "premium") return "purple";
    return "blue";
  }

  function valueFor(key: string) {
    const value = result?.parsed_intent?.[key];
    if (Array.isArray(value)) return value.join(", ");
    if (value === undefined || value === null || value === "") return "-";
    return String(value);
  }

  return (
    <div className="two-column">
      <Space direction="vertical" size={16} style={{ width: "100%" }}>
        <Card title={t("chat.title")}>
          <Space direction="vertical" size={12} style={{ width: "100%" }}>
            <Space wrap className="prompt-strip">
              {examples.map((example) => (
                <Button key={example} size="small" onClick={() => setInput(example)}>
                  {example.slice(0, 42)}...
                </Button>
              ))}
            </Space>
            <div className="chat-surface" aria-live="polite">
              {chat.length ? (
                chat.map((item, index) => (
                  <ChatMessage
                    key={`${item.role}-${index}`}
                    role={item.role === "agent" ? "assistant" : "user"}
                    content={item.content}
                    streaming={item.streaming}
                  />
                ))
              ) : (
                <div className="chat-empty">{t("chat.noMessages")}</div>
              )}
              {loading && chat[chat.length - 1]?.role === "user" ? (
                <div className="chat-row is-agent">
                  <div className="chat-avatar">
                    <LoadingOutlined />
                  </div>
                  <div className="chat-bubble">
                    <div className="typing-dots">
                      <span />
                      <span />
                      <span />
                    </div>
                  </div>
                </div>
              ) : null}
              <div ref={chatEndRef} />
            </div>
            <div className="composer">
              <Input.TextArea
                value={input}
                onChange={(event) => setInput(event.target.value)}
                onPressEnter={(event) => {
                  if (!event.shiftKey) {
                    event.preventDefault();
                    submit();
                  }
                }}
                autoSize={{ minRows: 2, maxRows: 5 }}
                disabled={loading}
                placeholder={loading ? t("chat.sending") : undefined}
              />
              <Button
                type="primary"
                shape="circle"
                icon={<SendOutlined />}
                loading={loading}
                disabled={loading || !input.trim()}
                onClick={() => submit()}
                aria-label={t("chat.send")}
              />
            </div>
            <Space wrap>
              <Button icon={<ShoppingCartOutlined />} disabled={!result} onClick={createOrder}>
                {t("chat.createOrder")}
              </Button>
              <Button icon={<SaveOutlined />} disabled={!result || !lastRequest} onClick={saveHistory}>
                Save History
              </Button>
              <Button icon={<CreditCardOutlined />} disabled={!order} onClick={() => order && pay(order)}>
                {t("chat.payWithStripe")}
              </Button>
              {paymentStatus ? (
                <Tag color={paymentStatus.payment_provider === "stripe" ? "green" : "blue"}>
                  {t("chat.paymentMode")}: {paymentStatus.payment_provider}
                </Tag>
              ) : null}
            </Space>
          </Space>
        </Card>
        <OrderSummary order={order} onPay={pay} />
        <Card
          title={
            <Space>
              <HistoryOutlined />
              Procurement History
            </Space>
          }
          extra={
            <Button size="small" onClick={refreshHistory} loading={historyLoading}>
              Refresh
            </Button>
          }
        >
          <List
            loading={historyLoading}
            dataSource={historyRecords}
            locale={{ emptyText: "No history" }}
            renderItem={(item) => (
              <List.Item
                actions={[
                  <Button key="restore" type="link" onClick={() => restoreHistory(item.id)}>
                    Restore
                  </Button>,
                  <Popconfirm
                    key="delete"
                    title="Delete this history record?"
                    okText="Delete"
                    okButtonProps={{ danger: true }}
                    onConfirm={() => deleteHistory(item.id)}
                  >
                    <Button type="text" danger icon={<DeleteOutlined />} aria-label="Delete history" />
                  </Popconfirm>
                ]}
              >
                <List.Item.Meta
                  title={item.original_request || item.id}
                  description={`${new Date(item.created_at).toLocaleString()} · $${item.total_cost.toFixed(2)}`}
                />
              </List.Item>
            )}
          />
        </Card>
      </Space>

      <Space direction="vertical" size={16} style={{ width: "100%" }}>
        <Card title={t("chat.parsedIntent")}>
          {result ? (
            <Space wrap style={{ marginBottom: 12 }}>
              <Tag color={result.used_mock_llm ? "orange" : "green"}>
                {t("chat.modelStatus")}: {result.model_provider} / {result.model_name}
              </Tag>
              <Tag color={result.used_previous_context ? "blue" : "default"}>
                {t("chat.previousContext")}:{" "}
                {result.used_previous_context ? t("chat.usingPreviousContext") : t("chat.newConversation")}
              </Tag>
              <Tag>{t("chat.trace")}: {result.trace_id}</Tag>
              {result.llm_error ? <Tag color="red">{result.llm_error}</Tag> : null}
            </Space>
          ) : null}
          {result ? (
            <Space direction="vertical" size={12} style={{ width: "100%" }}>
              <Descriptions column={1} size="small" bordered>
                <Descriptions.Item label="Team Size">{valueFor("people_count")}</Descriptions.Item>
                <Descriptions.Item label="Categories">{valueFor("categories")}</Descriptions.Item>
                <Descriptions.Item label="Budget">{valueFor("budget")}</Descriptions.Item>
                <Descriptions.Item label="Rating">{valueFor("min_rating")}</Descriptions.Item>
                <Descriptions.Item label="Delivery">{valueFor("max_delivery_days")}</Descriptions.Item>
                <Descriptions.Item label="Intent">{valueFor("revision_intent")}</Descriptions.Item>
              </Descriptions>
              <Collapse
                size="small"
                items={[
                  {
                    key: "raw-json",
                    label: "Raw JSON",
                    children: (
                      <Typography.Text code style={{ whiteSpace: "pre-wrap" }}>
                        {JSON.stringify(result.parsed_intent, null, 2)}
                      </Typography.Text>
                    )
                  }
                ]}
              />
            </Space>
          ) : (
            <Typography.Text code>{"{}"}</Typography.Text>
          )}
        </Card>
        <RetrievalEvidencePanel evidence={result?.retrieval_evidence} />
        {result?.plan_options?.length ? (
          <Card title="Compare Plans">
            <Space direction="vertical" size={12} style={{ width: "100%" }}>
              {result.plan_options.map((option) => (
                <Card
                  key={option.id}
                  size="small"
                  type="inner"
                  title={
                    <Space wrap>
                      <Typography.Text strong>{option.name}</Typography.Text>
                      <Tag color={strategyColor(option.strategy)}>{option.description}</Tag>
                    </Space>
                  }
                  extra={
                    <Button
                      type={result.selected_plan_id === option.id ? "primary" : "default"}
                      size="small"
                      onClick={() => selectPlan(option.id)}
                    >
                      {result.selected_plan_id === option.id ? "Selected" : "Select Plan"}
                    </Button>
                  }
                >
                  <Space size={18} wrap>
                    <Statistic title="Total" value={option.plan.total_amount} precision={2} prefix="$" />
                    <Statistic title="Items" value={option.plan.items.length} />
                    <Statistic
                      title="Avg Rating"
                      value={
                        option.plan.items.length
                          ? option.plan.items.reduce((sum, item) => sum + (item.rating || 0), 0) /
                            option.plan.items.length
                          : 0
                      }
                      precision={1}
                    />
                  </Space>
                </Card>
              ))}
            </Space>
          </Card>
        ) : null}
        {result?.recommended_plan ? (
          <Card title="Quick Optimization" size="small">
            <Space wrap>
              {quickActions.map((item) => (
                <Button
                  key={item.action}
                  icon={item.action === "regenerate" ? <RedoOutlined /> : <ThunderboltOutlined />}
                  loading={optimizing === item.action}
                  disabled={Boolean(optimizing)}
                  onClick={() => optimize(item.action)}
                >
                  {item.label}
                </Button>
              ))}
              <Button icon={<DownloadOutlined />} onClick={exportExcel}>
                Export Excel
              </Button>
            </Space>
          </Card>
        ) : null}
        <ProcurementPlanCard
          plan={result?.recommended_plan}
          products={result?.retrieved_products || []}
          onExportExcel={result?.recommended_plan ? exportExcel : undefined}
        />
      </Space>
    </div>
  );
}
