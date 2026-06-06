"use client";

import { App, Button, Card, Input, List, Popconfirm, Space, Tag, Typography } from "antd";
import {
  CreditCardOutlined,
  DeleteOutlined,
  HistoryOutlined,
  LoadingOutlined,
  SaveOutlined,
  SendOutlined,
  ShoppingCartOutlined
} from "@ant-design/icons";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useLanguage } from "@/lib/i18n";
import type { ChatResponse, Order, PaymentStatus, ProcurementHistoryRecord } from "@/lib/types";
import ChatMessage from "./ChatMessage";
import OrderSummary from "./OrderSummary";
import ProcurementPlanCard from "./ProcurementPlanCard";

type ChatLine = { role: "user" | "agent"; content: string; streaming?: boolean };

const STREAM_CHUNK_SIZE = 3;
const STREAM_INTERVAL_MS = 18;

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
          <Typography.Text code style={{ whiteSpace: "pre-wrap" }}>
            {result ? JSON.stringify(result.parsed_intent, null, 2) : "{}"}
          </Typography.Text>
        </Card>
        <ProcurementPlanCard plan={result?.recommended_plan} />
      </Space>
    </div>
  );
}
