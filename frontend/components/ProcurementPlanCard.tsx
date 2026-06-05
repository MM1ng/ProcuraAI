"use client";

import { CheckCircleOutlined, CopyOutlined, ExclamationCircleOutlined } from "@ant-design/icons";
import { App, Button, Card, Empty, Progress, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { currency } from "@/lib/format";
import { useLanguage } from "@/lib/i18n";
import type { PlanItem, ProcurementPlan } from "@/lib/types";

const statusColor: Record<string, string> = {
  within_budget: "green",
  no_budget_provided: "blue",
  over_budget: "red",
  valid: "green",
  insufficient_stock: "red",
  satisfied: "green",
  needs_review: "orange"
};

function buildPlanMarkdown(plan: ProcurementPlan): string {
  const lines: string[] = [];
  lines.push(`# ${plan.revision_note || "Procurement Plan"}`);
  lines.push("");
  lines.push(`**Total Amount:** ${currency(plan.total_amount)}`);
  if (plan.budget) {
    lines.push(`**Budget:** ${currency(plan.budget)}`);
    lines.push(`**Budget Status:** ${plan.budget_status}`);
  }
  if (plan.revision_type && plan.revision_type !== "new_plan") {
    lines.push(`**Revision Type:** ${plan.revision_type}`);
  }
  if (plan.revision_note && plan.revision_note !== "no_cheaper_option_found" && plan.revision_note !== "no_lower_cost_replacement_found") {
    lines.push(`**Note:** ${plan.revision_note}`);
  }
  if (plan.previous_total_amount) {
    lines.push(`**Previous Total:** ${currency(plan.previous_total_amount)}`);
  }
  if (plan.savings_amount) {
    lines.push(`**Savings:** ${currency(plan.savings_amount)}`);
  }
  lines.push("");
  lines.push("## Items");
  lines.push("");
  lines.push("| Product | Category | Qty | Unit Price | Subtotal | Delivery (days) |");
  lines.push("|---------|----------|-----|------------|----------|-----------------|");
  for (const item of plan.items) {
    lines.push(
      `| ${item.name} | ${item.category} | ${item.quantity} | ${currency(item.unit_price)} | ${currency(item.subtotal)} | ${item.delivery_days} |`
    );
  }
  return lines.join("\n");
}

export default function ProcurementPlanCard({ plan }: { plan?: ProcurementPlan | null }) {
  const { t, translateCategory, translateStatus } = useLanguage();
  const { message } = App.useApp();

  if (!plan) {
    return <Empty description={t("plan.empty")} />;
  }

  const handleCopyPlan = async () => {
    try {
      await navigator.clipboard.writeText(buildPlanMarkdown(plan));
      message.success(t("chat.copied"));
    } catch {
      message.error(t("chat.copyFailed"));
    }
  };

  const budgetUsage = plan.budget ? Math.min(100, Math.round((plan.total_amount / plan.budget) * 100)) : 0;
  const columns: ColumnsType<PlanItem> = [
    { title: t("plan.product"), dataIndex: "name", key: "name" },
    {
      title: t("plan.category"),
      dataIndex: "category",
      key: "category",
      width: 140,
      render: (value: string) => translateCategory(value)
    },
    { title: t("plan.qty"), dataIndex: "quantity", key: "quantity", width: 80 },
    {
      title: t("plan.unit"),
      dataIndex: "unit_price",
      key: "unit_price",
      width: 110,
      render: (value: number) => currency(value)
    },
    {
      title: t("plan.subtotal"),
      dataIndex: "subtotal",
      key: "subtotal",
      width: 120,
      render: (value: number) => currency(value)
    },
    { title: t("plan.delivery"), dataIndex: "delivery_days", key: "delivery_days", width: 100 }
  ];

  return (
    <Card
      title={t("plan.title")}
      extra={
        <Space>
          <Button
            type="text"
            size="small"
            icon={<CopyOutlined />}
            onClick={handleCopyPlan}
            aria-label={t("chat.copyPlan")}
          >
            {t("chat.copyPlan")}
          </Button>
          <Typography.Text strong>{currency(plan.total_amount)}</Typography.Text>
        </Space>
      }
    >
      <Space direction="vertical" size={14} style={{ width: "100%" }}>
        <Space wrap>
          <Tag color={statusColor[plan.budget_status] || "default"}>{translateStatus(plan.budget_status)}</Tag>
          <Tag color={statusColor[plan.inventory_status] || "default"}>{translateStatus(plan.inventory_status)}</Tag>
          <Tag color={statusColor[plan.constraint_satisfaction] || "default"}>
            {plan.constraint_satisfaction === "satisfied" ? <CheckCircleOutlined /> : <ExclamationCircleOutlined />}{" "}
            {translateStatus(plan.constraint_satisfaction)}
          </Tag>
          {plan.revision_type && plan.revision_type !== "new_plan" ? (
            <Tag color="purple">
              {t("plan.revision")}: {plan.revision_type}
            </Tag>
          ) : null}
          {plan.previous_total_amount ? (
            <Tag>
              {t("plan.previousTotal")}: {currency(plan.previous_total_amount)}
            </Tag>
          ) : null}
          {plan.savings_amount ? (
            <Tag color={plan.savings_amount > 0 ? "green" : "orange"}>
              {t("plan.savings")}: {currency(plan.savings_amount)}
            </Tag>
          ) : null}
          {plan.revision_note === "no_cheaper_option_found" ? (
            <Tag color="gold">No lower-cost alternative found</Tag>
          ) : null}
          {plan.revision_note === "no_lower_cost_replacement_found" ? (
            <Tag color="gold">No lower-cost replacement found</Tag>
          ) : null}
          {plan.replacement_categories?.length ? (
            <Tag color="blue">
              {t("plan.replacements")}: {plan.replacement_categories.map(translateCategory).join(", ")}
            </Tag>
          ) : null}
        </Space>
        {plan.budget ? (
          <Progress
            percent={budgetUsage}
            status={plan.budget_status === "over_budget" ? "exception" : "active"}
            format={() => `${currency(plan.total_amount)} / ${currency(plan.budget)}`}
          />
        ) : null}
        <Table
          rowKey="product_id"
          size="small"
          pagination={false}
          columns={columns}
          dataSource={plan.items}
          scroll={{ x: 760 }}
        />
      </Space>
    </Card>
  );
}
