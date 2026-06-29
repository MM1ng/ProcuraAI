"use client";

import { Card, Collapse, Descriptions, List, Space, Tag, Typography } from "antd";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useLanguage } from "@/lib/i18n";

function valueText(value: unknown) {
  if (Array.isArray(value)) return value.join(", ");
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export default function AdminRagEvidencePage() {
  const { t } = useLanguage();
  const [traces, setTraces] = useState<Record<string, unknown>[]>([]);

  useEffect(() => {
    async function load() {
      const result = await api.observabilityTraces();
      setTraces(result.items.filter((item) => item.retrieval_evidence));
    }
    void load();
  }, []);

  return (
    <main className="page">
      <div className="page-header">
        <h1 className="page-title">{t("nav.ragEvidence")}</h1>
      </div>
      <Space direction="vertical" size={16} style={{ width: "100%" }}>
        {traces.map((trace) => {
          const evidence = (trace.retrieval_evidence || {}) as Record<string, unknown>;
          const products = (evidence.products as Record<string, unknown>[]) || [];
          const policies = (evidence.policies as Record<string, unknown>[]) || [];
          const suppliers = (evidence.suppliers as Record<string, unknown>[]) || [];
          const constraints = (evidence.constraints as Record<string, unknown>) || {};
          return (
            <Card key={String(trace.trace_id)} title={String(trace.trace_id || "Trace")} className="panel-card">
              <Descriptions column={1} size="small" bordered>
                <Descriptions.Item label={t("admin.userQuery")}>{String(trace.user_query || "-")}</Descriptions.Item>
                <Descriptions.Item label="Retrieval Mode">{valueText(evidence.retrieval_mode)}</Descriptions.Item>
                <Descriptions.Item label="Retrieval Filters">{valueText(constraints)}</Descriptions.Item>
              </Descriptions>
              <Collapse
                style={{ marginTop: 12 }}
                items={[
                  {
                    key: "products",
                    label: `Product vector Top-K (${products.length})`,
                    children: (
                      <List
                        dataSource={products}
                        renderItem={(item) => (
                          <List.Item>
                            <Space direction="vertical" size={2}>
                              <Typography.Text strong>{valueText(item.name)}</Typography.Text>
                              <Typography.Text>
                                {valueText(item.category)} · score {valueText(item.score)} · {valueText(item.reason)}
                              </Typography.Text>
                              <Tag>{valueText(item.supplier)}</Tag>
                            </Space>
                          </List.Item>
                        )}
                      />
                    )
                  },
                  {
                    key: "policies",
                    label: `Policy Evidence (${policies.length})`,
                    children: <Typography.Text code style={{ whiteSpace: "pre-wrap" }}>{JSON.stringify(policies, null, 2)}</Typography.Text>
                  },
                  {
                    key: "suppliers",
                    label: `Merchant Evidence (${suppliers.length})`,
                    children: <Typography.Text code style={{ whiteSpace: "pre-wrap" }}>{JSON.stringify(suppliers, null, 2)}</Typography.Text>
                  }
                ]}
              />
            </Card>
          );
        })}
      </Space>
    </main>
  );
}
