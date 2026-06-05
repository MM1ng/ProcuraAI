"use client";

import { Card } from "antd";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useLanguage } from "@/lib/i18n";

export default function EvaluationCharts({ results }: { results: Record<string, unknown>[] }) {
  const { t } = useLanguage();

  return (
    <Card title={t("evaluation.scores")}>
      <div style={{ width: "100%", height: 300 }}>
        <ResponsiveContainer>
          <BarChart data={results}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="log_id" />
            <YAxis domain={[0, 1]} />
            <Tooltip />
            <Bar dataKey="context_precision" fill="#2563eb" />
            <Bar dataKey="faithfulness" fill="#16a34a" />
            <Bar dataKey="answer_relevance" fill="#f59e0b" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}
