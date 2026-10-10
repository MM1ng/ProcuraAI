"use client";

import { Alert, Card, Space, Table, Tag } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useEffect, useState } from "react";
import OrderSummary from "@/components/OrderSummary";
import { api } from "@/lib/api";
import { currency } from "@/lib/format";
import { useLanguage } from "@/lib/i18n";
import type { Order } from "@/lib/types";

export default function OrdersPage() {
  const { t, translateStatus } = useLanguage();
  const [orders, setOrders] = useState<Order[]>([]);
  const [selected, setSelected] = useState<Order | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      await api.callerContext();
      const result = await api.orders();
      setOrders(result.items);
      setSelected(result.items[0] ?? null);
      setError(null);
    } catch (e) {
      setOrders([]); setSelected(null);
      setError(e instanceof Error ? e.message : "当前浏览器无法读取订单。");
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const columns: ColumnsType<Order> = [
    { title: t("orders.order"), dataIndex: "order_id", key: "order_id" },
    { title: t("orders.user"), dataIndex: "user_id", key: "user_id" },
    { title: t("orders.total"), dataIndex: "total_amount", key: "total_amount", render: currency },
    { title: t("orders.created"), dataIndex: "created_at", key: "created_at" },
    {
      title: t("orders.status"),
      dataIndex: "status",
      key: "status",
      render: (value: string) => <Tag color={value === "paid" ? "green" : "blue"}>{translateStatus(value)}</Tag>
    }
  ];

  return (
    <main className="page">
      <div className="page-header">
        <h1 className="page-title">{t("orders.title")}</h1>
      </div>
      <Space direction="vertical" size={16} style={{ width: "100%" }}>
        {error ? <Alert type="warning" message="订单当前不可访问" description={error} showIcon /> : null}
        <Card>
          <Table
            rowKey="order_id"
            columns={columns}
            dataSource={orders}
            pagination={{ pageSize: 8 }}
            onRow={(record) => ({ onClick: () => setSelected(record) })}
          />
        </Card>
        <OrderSummary order={selected} />
      </Space>
    </main>
  );
}
