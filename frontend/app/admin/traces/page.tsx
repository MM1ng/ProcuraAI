"use client";

import { Card, Descriptions, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useLanguage } from "@/lib/i18n";

export default function AdminTracesPage() {
  const { t } = useLanguage();
  const [traces, setTraces] = useState<Record<string, unknown>[]>([]);
  const [selected, setSelected] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    async function load() {
      const result = await api.observabilityTraces();
      setTraces(result.items);
      setSelected(result.items[0] || null);
    }
    void load();
  }, []);

  const columns: ColumnsType<Record<string, unknown>> = [
    { title: "Trace ID", dataIndex: "trace_id", key: "trace_id", ellipsis: true },
    { title: t("admin.sessionId"), dataIndex: "session_id", key: "session_id", ellipsis: true },
    { title: t("admin.userQuery"), dataIndex: "user_query", key: "user_query", ellipsis: true },
    { title: t("observability.model"), key: "model", render: (_, record) => `${record.model_used || record.model_name || "-"}` },
    { title: t("admin.fallback"), dataIndex: "fallback_triggered", key: "fallback_triggered", render: (value) => <Tag color={value ? "purple" : "default"}>{String(Boolean(value))}</Tag> },
    { title: t("observability.latency"), dataIndex: "latency_ms", key: "latency_ms" },
    { title: t("admin.error"), dataIndex: "error", key: "error", ellipsis: true }
  ];

  return (
    <main className="page">
      <div className="page-header">
        <h1 className="page-title">{t("nav.traces")}</h1>
      </div>
      <Card title={t("admin.traceList")} className="panel-card">
        <Table
          rowKey={(record) => String(record.log_id || record.trace_id)}
          columns={columns}
          dataSource={traces}
          pagination={{ pageSize: 8 }}
          onRow={(record) => ({ onClick: () => setSelected(record) })}
        />
      </Card>
      {selected ? (
        <Card title={t("admin.traceDetail")} className="panel-card">
          <Descriptions column={1} bordered size="small">
            <Descriptions.Item label="Trace ID">{String(selected.trace_id || "-")}</Descriptions.Item>
            <Descriptions.Item label={t("admin.sessionId")}>{String(selected.session_id || "-")}</Descriptions.Item>
            <Descriptions.Item label={t("admin.userQuery")}>{String(selected.user_query || "-")}</Descriptions.Item>
            <Descriptions.Item label={t("admin.response")}>{String(selected.final_answer || "-")}</Descriptions.Item>
            <Descriptions.Item label={t("observability.model")}>{String(selected.model_used || selected.model_name || "-")}</Descriptions.Item>
            <Descriptions.Item label={t("admin.fallback")}>{String(Boolean(selected.fallback_triggered))}</Descriptions.Item>
            <Descriptions.Item label={t("admin.fallbackReason")}>{String(selected.fallback_reason || "-")}</Descriptions.Item>
            <Descriptions.Item label={t("observability.latency")}>{String(selected.latency_ms || "-")} ms</Descriptions.Item>
            <Descriptions.Item label={t("admin.error")}>{String(selected.error || selected.llm_error || "-")}</Descriptions.Item>
          </Descriptions>
          <Typography.Title level={5}>{t("admin.rawJson")}</Typography.Title>
          <Typography.Text code style={{ whiteSpace: "pre-wrap" }}>
            {JSON.stringify(selected, null, 2)}
          </Typography.Text>
        </Card>
      ) : null}
    </main>
  );
}
