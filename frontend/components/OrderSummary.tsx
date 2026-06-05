"use client";

import { Button, Card, Descriptions, Table, Tag } from "antd";
import type { ColumnsType } from "antd/es/table";
import { CreditCardOutlined } from "@ant-design/icons";
import { currency } from "@/lib/format";
import { useLanguage } from "@/lib/i18n";
import type { Order, PlanItem } from "@/lib/types";

export default function OrderSummary({
  order,
  onPay
}: {
  order: Order | null;
  onPay?: (order: Order) => void;
}) {
  const { t, translateStatus } = useLanguage();

  if (!order) return null;

  const columns: ColumnsType<PlanItem> = [
    { title: t("plan.product"), dataIndex: "name", key: "name" },
    { title: t("plan.qty"), dataIndex: "quantity", key: "quantity", width: 80 },
    { title: t("plan.unit"), dataIndex: "unit_price", key: "unit_price", render: currency },
    { title: t("plan.subtotal"), dataIndex: "subtotal", key: "subtotal", render: currency }
  ];

  return (
    <Card
      title={t("orders.confirmation")}
      extra={
        onPay ? (
          <Button type="primary" icon={<CreditCardOutlined />} onClick={() => onPay(order)}>
            {t("chat.payWithStripe")}
          </Button>
        ) : null
      }
    >
      <Descriptions size="small" column={2}>
        <Descriptions.Item label={t("orders.order")}>{order.order_id}</Descriptions.Item>
        <Descriptions.Item label={t("orders.status")}>
          <Tag color={order.status === "paid" ? "green" : "blue"}>{translateStatus(order.status)}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label={t("orders.user")}>{order.user_id}</Descriptions.Item>
        <Descriptions.Item label={t("orders.total")}>{currency(order.total_amount)}</Descriptions.Item>
      </Descriptions>
      <Table
        rowKey="order_item_id"
        size="small"
        pagination={false}
        columns={columns}
        dataSource={order.order_items}
        style={{ marginTop: 12 }}
      />
    </Card>
  );
}
