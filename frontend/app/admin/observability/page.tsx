"use client";

import { Card, Table, Tag } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useEffect, useState } from "react";
import MetricCard from "@/components/MetricCard";
import { LatencyTrendChart, ToolCallDistributionChart } from "@/components/ObservabilityCharts";
import { api } from "@/lib/api";
import { percent } from "@/lib/format";
import { useLanguage } from "@/lib/i18n";

export default function ObservabilityPage() {
  const { t } = useLanguage();
  const [summary, setSummary] = useState<Record<string, unknown>>({});
  const [traces, setTraces] = useState<Record<string, unknown>[]>([]);

  async function load() {
    const [summaryResult, tracesResult] = await Promise.all([
      api.observabilitySummary(),
      api.observabilityTraces()
    ]);
    setSummary(summaryResult);
    setTraces(tracesResult.items);
  }

  useEffect(() => {
    void load();
  }, []);

  const columns: ColumnsType<Record<string, unknown>> = [
    { title: t("observability.created"), dataIndex: "created_at", key: "created_at" },
    { title: t("intent.intent"), key: "intent", render: (_, record) => String((record.parsed_intent as Record<string, unknown> | undefined)?.intent || "-") },
    { title: t("observability.trace"), dataIndex: "trace_id", key: "trace_id" },
    { title: t("observability.query"), dataIndex: "user_query", key: "user_query", ellipsis: true },
    {
      title: t("observability.model"),
      key: "model",
      render: (_, record) => `${record.model_provider || "-"} / ${record.model_name || "-"}`
    },
    {
      title: t("observability.toolCalls"),
      key: "tool_calls",
      render: (_, record) => Array.isArray(record.tool_calls) ? record.tool_calls.length : "-"
    },
    {
      title: t("observability.mock"),
      dataIndex: "used_mock_llm",
      key: "used_mock_llm",
      render: (value: boolean) => <Tag color={value ? "orange" : "green"}>{String(Boolean(value))}</Tag>
    },
    { title: t("observability.llmError"), dataIndex: "llm_error", key: "llm_error", ellipsis: true },
    { title: t("observability.latency"), dataIndex: "latency_ms", key: "latency_ms" }
  ];

  return (
    <main className="page">
      <div className="page-header">
        <h1 className="page-title">{t("observability.title")}</h1>
      </div>
      <div className="metric-grid">
        <MetricCard title={t("observability.totalConversations")} value={Number(summary.total_conversations ?? 0)} />
        <MetricCard title={t("observability.averageLatency")} value={Number(summary.average_latency ?? 0)} suffix="ms" />
        <MetricCard
          title={t("observability.toolCallSuccessRate")}
          value={percent(Number(summary.tool_call_success_rate ?? 0))}
        />
        <MetricCard
          title={t("observability.retrievalSuccessRate")}
          value={percent(Number(summary.retrieval_success_rate ?? 0))}
        />
        <MetricCard
          title={t("observability.paymentSuccessRate")}
          value={percent(Number(summary.payment_success_rate ?? 0))}
        />
        <MetricCard title={t("observability.errorRate")} value={percent(Number(summary.error_rate ?? 0))} />
      </div>
      <div className="two-column">
        <LatencyTrendChart data={(summary.latency_trend as Record<string, unknown>[]) || []} />
        <ToolCallDistributionChart data={(summary.tool_call_distribution as Record<string, unknown>[]) || []} />
      </div>
      <Card title={t("observability.recentTraces")} className="panel-card">
        <Table rowKey="log_id" columns={columns} dataSource={traces} pagination={{ pageSize: 8 }} />
      </Card>
    </main>
  );
}
