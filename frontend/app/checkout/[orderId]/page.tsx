"use client";

import { Button, Card, Descriptions, Result, Space, Spin, Table, Tag, Typography } from "antd";
import { CheckCircleOutlined, HomeOutlined, OrderedListOutlined } from "@ant-design/icons";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { currency } from "@/lib/format";
import type { Order } from "@/lib/types";

export default function CheckoutPage() {
  const params = useParams();
  const router = useRouter();
  const orderId = params?.orderId as string;
  const [order, setOrder] = useState<Order | null>(null);
  const [loading, setLoading] = useState(true);
  const [paying, setPaying] = useState(false);
  const [paid, setPaid] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!orderId) return;
    api.getOrder(orderId)
      .then(o => { setOrder(o); if (o.status === "paid") setPaid(true); })
      .catch(e => setError(e instanceof Error ? e.message : "Failed"))
      .finally(() => setLoading(false));
  }, [orderId]);

  async function handleMockPay() {
    if (!orderId) return;
    setPaying(true); setError(null);
    try {
      const r = await api.mockPaymentSuccess(orderId);
      if (r.status === "paid") { setPaid(true); if (r.order) setOrder(r.order); }
    } catch (e) { setError(e instanceof Error ? e.message : "Payment failed"); }
    finally { setPaying(false); }
  }

  if (loading) return <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "60vh" }}><Spin size="large" /></div>;
  if (error && !order) return <Result status="error" title="Failed" subTitle={error} extra={<Button onClick={() => router.push("/chat")}>Back to Chat</Button>} />;

  if (paid) return (
    <div style={{ maxWidth: 600, margin: "40px auto" }}>
      <Result status="success" title="Payment Successful" subTitle={`Order ${order?.order_id} has been paid. Total: ${currency(order?.total_amount ?? 0)}`}
        extra={[<Button key="chat" type="primary" icon={<HomeOutlined />} onClick={() => router.push("/chat")}>Back to Chat</Button>, <Button key="orders" icon={<OrderedListOutlined />} onClick={() => router.push("/orders")}>View Orders</Button>]} />
      {order ? <Card title="Order Summary" style={{ marginTop: 16 }}><Descriptions column={1} size="small" bordered><Descriptions.Item label="Order ID">{order.order_id}</Descriptions.Item><Descriptions.Item label="Status"><Tag color="green" icon={<CheckCircleOutlined />}>Paid</Tag></Descriptions.Item><Descriptions.Item label="Total">{currency(order.total_amount)}</Descriptions.Item><Descriptions.Item label="Created">{new Date(order.created_at).toLocaleString()}</Descriptions.Item></Descriptions></Card> : null}
    </div>
  );

  return (
    <div style={{ maxWidth: 800, margin: "40px auto" }}>
      <Card title="Checkout" extra={<Tag color="orange">Pending Payment</Tag>}>
        <Space direction="vertical" size={16} style={{ width: "100%" }}>
          <Descriptions column={2} size="small" bordered>
            <Descriptions.Item label="Order ID">{order?.order_id || "-"}</Descriptions.Item>
            <Descriptions.Item label="Status">{order?.status || "-"}</Descriptions.Item>
            <Descriptions.Item label="Total">{currency(order?.total_amount ?? 0)}</Descriptions.Item>
            <Descriptions.Item label="Created">{order?.created_at ? new Date(order.created_at).toLocaleString() : "-"}</Descriptions.Item>
          </Descriptions>
          {order?.order_items?.length ? <>
            <Typography.Text strong>Order Items</Typography.Text>
            <Table rowKey="product_id" size="small" pagination={false} dataSource={order.order_items} columns={[
              { title: "Product", dataIndex: "name", key: "name" }, { title: "Qty", dataIndex: "quantity", key: "qty", width: 80 },
              { title: "Unit", dataIndex: "unit_price", key: "up", width: 110, render: (v: number) => currency(v) },
              { title: "Subtotal", dataIndex: "subtotal", key: "sub", width: 120, render: (v: number) => currency(v) },
            ]} />
          </> : null}
          {error ? <Typography.Text type="danger">{error}</Typography.Text> : null}
          <div style={{ textAlign: "center", marginTop: 16 }}>
            <Space size={16}>
              <Button type="primary" size="large" loading={paying} onClick={handleMockPay}>Simulate Payment Success</Button>
              <Button size="large" onClick={() => router.push("/chat")}>Back to Chat</Button>
            </Space>
          </div>
          <Typography.Text type="secondary" style={{ textAlign: "center", display: "block" }}>Mock payment page. Production: redirect to Stripe Checkout.</Typography.Text>
        </Space>
      </Card>
    </div>
  );
}
