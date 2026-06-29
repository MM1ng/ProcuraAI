"use client";

import { Button, Card, Table } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useEffect, useState } from "react";
import EvaluationCharts from "@/components/EvaluationCharts";
import MetricCard from "@/components/MetricCard";
import { api } from "@/lib/api";
import { percent } from "@/lib/format";
import { useLanguage } from "@/lib/i18n";

export default function EvaluationPage() {
  const { t } = useLanguage();
  const [summary, setSummary] = useState<Record<string, unknown>>({});
  const results = ((summary.results as Record<string, unknown>[]) || []) as Record<string, unknown>[];

  async function load() {
    setSummary(await api.evaluationSummary());
  }

  async function runMock() {
    await api.runMockEvaluation();
    await load();
  }

  async function runAgent() {
    await api.runAgentEvaluation();
    await load();
  }

  useEffect(() => {
    void load();
  }, []);

  const columns: ColumnsType<Record<string, unknown>> = [
    { title: t("evaluation.question"), dataIndex: "question", key: "question", ellipsis: true },
    { title: t("evaluation.precision"), dataIndex: "context_precision", key: "context_precision" },
    { title: t("evaluation.recall"), dataIndex: "context_recall", key: "context_recall" },
    { title: t("evaluation.faithfulness"), dataIndex: "faithfulness", key: "faithfulness" },
    { title: t("observability.latency"), dataIndex: "latency_ms", key: "latency_ms" }
  ];

  return (
    <main className="page">
      <div className="page-header">
        <h1 className="page-title">{t("evaluation.title")}</h1>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <Button onClick={runMock}>{t("evaluation.runMock")}</Button>
          <Button type="primary" onClick={runAgent}>
            {t("evaluation.runAgent")}
          </Button>
        </div>
      </div>
      <div className="metric-grid">
        <MetricCard title={t("evaluation.contextPrecision")} value={percent(Number(summary.context_precision ?? 0))} />
        <MetricCard title={t("evaluation.contextRecall")} value={percent(Number(summary.context_recall ?? 0))} />
        <MetricCard title={t("evaluation.faithfulness")} value={percent(Number(summary.faithfulness ?? 0))} />
        <MetricCard title={t("evaluation.answerRelevance")} value={percent(Number(summary.answer_relevance ?? 0))} />
        <MetricCard
          title={t("evaluation.budgetComplianceRate")}
          value={percent(Number(summary.budget_compliance_rate ?? 0))}
        />
        <MetricCard
          title={t("evaluation.inventoryValidityRate")}
          value={percent(Number(summary.inventory_validity_rate ?? 0))}
        />
        <MetricCard
          title={t("evaluation.constraintSatisfactionRate")}
          value={percent(Number(summary.constraint_satisfaction_rate ?? 0))}
        />
        <MetricCard
          title={t("evaluation.purchaseCompletionRate")}
          value={percent(Number(summary.purchase_completion_rate ?? 0))}
        />
        <MetricCard title={t("evaluation.averageLatency")} value={Number(summary.average_latency ?? 0)} suffix="ms" />
      </div>
      <EvaluationCharts results={results} />
      <Card title={t("evaluation.results")}>
        <Table rowKey="log_id" columns={columns} dataSource={results} pagination={{ pageSize: 8 }} />
      </Card>
    </main>
  );
}
