"use client";

import { Card, Table, Tag } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useEffect, useState } from "react";
import MetricCard from "@/components/MetricCard";
import { api } from "@/lib/api";
import { percent } from "@/lib/format";
import { useLanguage } from "@/lib/i18n";

export default function AdminDashboardPage() {
  const { t } = useLanguage();
  const [summary, setSummary] = useState<Record<string, unknown>>({});
  const [traces, setTraces] = useState<Record<string, unknown>[]>([]);

  useEffect(() => {
    async function load() {
      const [observability, orders, traceResult] = await Promise.all([
        api.observabilitySummary(),
        api.orders(),
        api.observabilityTraces()
      ]);
      setSummary({
        ...observability,
        successful_orders: orders.items.filter((item) => item.status === "paid" || item.status === "completed").length,
        payment_conversion_rate: orders.total ? orders.items.filter((item) => item.status === "paid").length / orders.total : 0
      });
      setTraces(traceResult.items.slice(0, 6));
    }
    void load();
  }, []);

  const columns: ColumnsType<Record<string, unknown>> = [
    { title: "Trace ID", dataIndex: "trace_id", key: "trace_id", ellipsis: true },
    { title: t("admin.userQuery"), dataIndex: "user_query", key: "user_query", ellipsis: true },
    { title: t("intent.intent"), key: "intent", render: (_, record) => String((record.parsed_intent as Record<string, unknown> | undefined)?.intent || "-") },
    { title: t("observability.model"), key: "model", render: (_, record) => `${record.model_used || record.model_name || "-"}` },
    { title: t("observability.latency"), dataIndex: "latency_ms", key: "latency_ms" },
    { title: t("admin.error"), dataIndex: "error", key: "error", ellipsis: true }
  ];

  return (
    <main className="page">
      <div className="page-header">
        <h1 className="page-title">{t("nav.adminDashboard")}</h1>
        <Tag color="purple">{t("admin.technicalConsole")}</Tag>
      </div>
      <div className="metric-grid">
        <MetricCard title={t("admin.totalConversations")} value={Number(summary.total_conversations ?? 0)} />
        <MetricCard title={t("admin.productSearches")} value={Number(summary.product_search_count ?? 0)} />
        <MetricCard title={t("admin.recommendationsGenerated")} value={Number(summary.total_conversations ?? 0)} />
        <MetricCard title={t("admin.ordersCreated")} value={Number(summary.successful_orders ?? 0)} />
        <MetricCard title={t("admin.checkoutConversion")} value={percent(Number(summary.payment_conversion_rate ?? 0))} />
        <MetricCard title={t("observability.averageLatency")} value={Number(summary.average_latency ?? 0)} suffix="ms" />
        <MetricCard title={t("admin.retrievalHitRate")} value={percent(Number(summary.retrieval_success_rate ?? 0))} />
        <MetricCard title={t("admin.errorCount")} value={Number(summary.error_count ?? 0)} />
      </div>
      <Card title={t("admin.recentActivity")} className="panel-card">
        <Table rowKey={(record) => String(record.log_id || record.trace_id)} columns={columns} dataSource={traces} pagination={false} />
      </Card>
    </main>
  );
}
