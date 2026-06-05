"use client";

import { Card, Descriptions, Empty, Space } from "antd";
import { useEffect, useState } from "react";
import ProcurementPlanCard from "@/components/ProcurementPlanCard";
import { currency } from "@/lib/format";
import { useLanguage } from "@/lib/i18n";
import type { ProcurementPlan } from "@/lib/types";

export default function ProcurementPage() {
  const { t, translateStatus } = useLanguage();
  const [plan, setPlan] = useState<ProcurementPlan | null>(null);

  useEffect(() => {
    const stored = localStorage.getItem("currentPlan");
    if (stored) setPlan(JSON.parse(stored) as ProcurementPlan);
  }, []);

  return (
    <main className="page">
      <div className="page-header">
        <h1 className="page-title">{t("nav.procurement")}</h1>
      </div>
      {plan ? (
        <Space direction="vertical" size={16} style={{ width: "100%" }}>
          <Card>
            <Descriptions column={4} size="small">
              <Descriptions.Item label={t("orders.total")}>{currency(plan.total_amount)}</Descriptions.Item>
              <Descriptions.Item label={t("plan.budget")}>
                {plan.budget ? currency(plan.budget) : t("plan.notProvided")}
              </Descriptions.Item>
              <Descriptions.Item label={t("plan.inventory")}>{translateStatus(plan.inventory_status)}</Descriptions.Item>
              <Descriptions.Item label={t("plan.constraints")}>
                {translateStatus(plan.constraint_satisfaction)}
              </Descriptions.Item>
            </Descriptions>
          </Card>
          <ProcurementPlanCard plan={plan} />
        </Space>
      ) : (
        <Empty description={t("plan.empty")} />
      )}
    </main>
  );
}
