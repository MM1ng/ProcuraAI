"use client";

import { CheckCircleOutlined, CopyOutlined, CreditCardOutlined, ExclamationCircleOutlined, FileExcelOutlined, ShoppingCartOutlined } from "@ant-design/icons";
import { App, Button, Card, Empty, Progress, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useMemo, useState } from "react";
import { currency } from "@/lib/format";
import { useLanguage } from "@/lib/i18n";
import type { CartItem, PlanItem, ProcurementPlan, Product } from "@/lib/types";
import ProductDetailModal from "./ProductDetailModal";

const statusColor: Record<string, string> = {
  within_budget: "green", no_budget_provided: "blue", over_budget: "red",
  valid: "green", insufficient_stock: "red", satisfied: "green", needs_review: "orange",
};

function buildPlanMarkdown(plan: ProcurementPlan): string {
  const lines = [`# ${plan.revision_note || "Procurement Plan"}`, "",
    `**Total:** ${currency(plan.total_amount)}`];
  if (plan.budget) { lines.push(`**Budget:** ${currency(plan.budget)}`, `**Budget Status:** ${plan.budget_status}`); }
  lines.push("", "## Items", "", "| Product | Category | Qty | Unit | Subtotal | Delivery |",
    "|---------|----------|-----|------|----------|----------|");
  for (const i of plan.items) lines.push(`| ${i.name} | ${i.category} | ${i.quantity} | ${currency(i.unit_price)} | ${currency(i.subtotal)} | ${i.delivery_days} |`);
  return lines.join("\n");
}

function enrichItem(item: PlanItem, products: Product[]): PlanItem {
  const p = products.find(c => c.product_id === item.product_id);
  return { ...item, description: item.description || p?.description || "", brand: item.brand || p?.brand, supplier: item.supplier || p?.supplier, rating: item.rating ?? p?.rating, stock: item.stock ?? p?.stock, delivery_days: item.delivery_days ?? p?.delivery_days };
}

export default function ProcurementPlanCard({
  plan, products = [], onExportExcel, onAddToCart, onCreateOrder, onPayPlan, creatingOrder, payingPlan,
}: {
  plan?: ProcurementPlan | null; products?: Product[]; onExportExcel?: () => void;
  onAddToCart?: (items: CartItem[]) => void; onCreateOrder?: () => void;
  onPayPlan?: () => void; creatingOrder?: boolean; payingPlan?: boolean;
}) {
  const { t, translateCategory, translateStatus } = useLanguage();
  const { message } = App.useApp();
  const [detail, setDetail] = useState<PlanItem | null>(null);
  const enriched = useMemo(() => plan?.items.map(i => enrichItem(i, products)) || [], [plan, products]);
  if (!plan) return <Empty description={t("plan.empty")} />;

  const budgetUsage = plan.budget ? Math.min(100, Math.round((plan.total_amount / plan.budget) * 100)) : 0;
  const cols: ColumnsType<PlanItem> = [
    { title: t("plan.product"), dataIndex: "name", key: "name", render: (v: string, item) => <Button type="link" size="small" onClick={() => setDetail(item)}>{v}</Button> },
    { title: t("plan.category"), dataIndex: "category", key: "category", width: 140, render: (v: string) => translateCategory(v) },
    { title: t("plan.qty"), dataIndex: "quantity", key: "quantity", width: 80 },
    { title: t("plan.unit"), dataIndex: "unit_price", key: "unit_price", width: 110, render: (v: number) => currency(v) },
    { title: t("plan.subtotal"), dataIndex: "subtotal", key: "subtotal", width: 120, render: (v: number) => currency(v) },
    { title: t("plan.delivery"), dataIndex: "delivery_days", key: "delivery_days", width: 100 },
  ];
  const hasActions = !!(onAddToCart || onCreateOrder || onPayPlan);

  return (
    <Card title={t("plan.title")} extra={<Space>
      <Button type="text" size="small" icon={<CopyOutlined />} onClick={async () => { try { await navigator.clipboard.writeText(buildPlanMarkdown(plan)); message.success(t("chat.copied")); } catch { message.error(t("chat.copyFailed")); } }}>{t("chat.copyPlan")}</Button>
      {onExportExcel ? <Button type="text" size="small" icon={<FileExcelOutlined />} onClick={onExportExcel}>Export Excel</Button> : null}
      <Typography.Text strong>{currency(plan.total_amount)}</Typography.Text>
    </Space>}>
      <Space direction="vertical" size={14} style={{ width: "100%" }}>
        <Space wrap>
          <Tag color={statusColor[plan.budget_status] || "default"}>{translateStatus(plan.budget_status)}</Tag>
          <Tag color={statusColor[plan.inventory_status] || "default"}>{translateStatus(plan.inventory_status)}</Tag>
          <Tag color={statusColor[plan.constraint_satisfaction] || "default"}>
            {plan.constraint_satisfaction === "satisfied" ? <CheckCircleOutlined /> : <ExclamationCircleOutlined />} {translateStatus(plan.constraint_satisfaction)}
          </Tag>
          {plan.revision_type && plan.revision_type !== "new_plan" ? <Tag color="purple">{t("plan.revision")}: {plan.revision_type}</Tag> : null}
          {plan.previous_total_amount ? <Tag>{t("plan.previousTotal")}: {currency(plan.previous_total_amount)}</Tag> : null}
          {plan.savings_amount ? <Tag color={plan.savings_amount > 0 ? "green" : "orange"}>{t("plan.savings")}: {currency(plan.savings_amount)}</Tag> : null}
        </Space>
        {plan.budget ? <Progress percent={budgetUsage} status={plan.budget_status === "over_budget" ? "exception" : "active"} format={() => `${currency(plan.total_amount)} / ${currency(plan.budget)}`} /> : null}
        <Table rowKey="product_id" size="small" pagination={false} columns={cols} dataSource={enriched} scroll={{ x: 760 }} onRow={(item) => ({ onDoubleClick: () => setDetail(item) })} />
        {hasActions ? <Space style={{ marginTop: 8 }}>
          {onAddToCart ? <Button icon={<ShoppingCartOutlined />} onClick={() => onAddToCart(enriched.map(i => ({ product_id: i.product_id, name: i.name, brand: i.brand, category: i.category, price: i.unit_price, quantity: i.quantity, supplier: i.supplier, delivery_days: i.delivery_days, stock: i.stock, rating: i.rating })))}>Add All to Cart</Button> : null}
          {onCreateOrder ? <Button type="primary" loading={creatingOrder} onClick={onCreateOrder}>Create Order</Button> : null}
          {onPayPlan ? <Button type="primary" icon={<CreditCardOutlined />} loading={payingPlan} onClick={onPayPlan}>Pay Now</Button> : null}
        </Space> : null}
      </Space>
      <ProductDetailModal open={Boolean(detail)} item={detail} onClose={() => setDetail(null)} />
    </Card>
  );
}
