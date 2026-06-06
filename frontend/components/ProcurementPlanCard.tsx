"use client";

import { CheckCircleOutlined, CopyOutlined, ExclamationCircleOutlined, FileExcelOutlined } from "@ant-design/icons";
import { App, Button, Card, Descriptions, Empty, Modal, Progress, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useMemo, useState } from "react";
import { currency } from "@/lib/format";
import { useLanguage } from "@/lib/i18n";
import type { PlanItem, ProcurementPlan, Product } from "@/lib/types";

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

function enrichItem(item: PlanItem, products: Product[]): PlanItem {
  const product = products.find((candidate) => candidate.product_id === item.product_id);
  return {
    ...item,
    description: item.description || product?.description || "",
    brand: item.brand || product?.brand,
    supplier: item.supplier || product?.supplier,
    rating: item.rating ?? product?.rating,
    stock: item.stock ?? product?.stock,
    delivery_days: item.delivery_days ?? product?.delivery_days
  };
}

export default function ProcurementPlanCard({
  plan,
  products = [],
  onExportExcel
}: {
  plan?: ProcurementPlan | null;
  products?: Product[];
  onExportExcel?: () => void;
}) {
  const { t, translateCategory, translateStatus } = useLanguage();
  const { message } = App.useApp();
  const [detailItem, setDetailItem] = useState<PlanItem | null>(null);
  const enrichedItems = useMemo(() => plan?.items.map((item) => enrichItem(item, products)) || [], [plan, products]);

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
    {
      title: t("plan.product"),
      dataIndex: "name",
      key: "name",
      render: (value: string, item) => (
        <Button type="link" size="small" onClick={() => setDetailItem(item)}>
          {value}
        </Button>
      )
    },
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
          {onExportExcel ? (
            <Button type="text" size="small" icon={<FileExcelOutlined />} onClick={onExportExcel}>
              Export Excel
            </Button>
          ) : null}
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
          dataSource={enrichedItems}
          scroll={{ x: 760 }}
          onRow={(item) => ({ onDoubleClick: () => setDetailItem(item) })}
        />
      </Space>
      <Modal
        title={detailItem?.name || "Product Detail"}
        open={Boolean(detailItem)}
        onCancel={() => setDetailItem(null)}
        footer={null}
      >
        {detailItem ? (
          <Descriptions column={1} size="small" bordered>
            <Descriptions.Item label="Name">{detailItem.name}</Descriptions.Item>
            <Descriptions.Item label="Category">{translateCategory(detailItem.category)}</Descriptions.Item>
            <Descriptions.Item label="Brand">{detailItem.brand || "-"}</Descriptions.Item>
            <Descriptions.Item label="Supplier">{detailItem.supplier || "-"}</Descriptions.Item>
            <Descriptions.Item label="Price">{currency(detailItem.unit_price)}</Descriptions.Item>
            <Descriptions.Item label="Rating">{detailItem.rating ?? "-"}</Descriptions.Item>
            <Descriptions.Item label="Stock">{detailItem.stock ?? "-"}</Descriptions.Item>
            <Descriptions.Item label="Delivery Days">{detailItem.delivery_days ?? "-"}</Descriptions.Item>
            <Descriptions.Item label="Description">{detailItem.description || "-"}</Descriptions.Item>
            <Descriptions.Item label="Why Selected">{detailItem.reason || "-"}</Descriptions.Item>
          </Descriptions>
        ) : null}
      </Modal>
    </Card>
  );
}
