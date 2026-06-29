"use client";

import { Button, Drawer, InputNumber, List, Space, Tag, Typography, App } from "antd";
import { CreditCardOutlined, DeleteOutlined, ShoppingCartOutlined } from "@ant-design/icons";
import { currency } from "@/lib/format";
import { useLanguage } from "@/lib/i18n";
import type { CartItem, Order } from "@/lib/types";
import { api } from "@/lib/api";

export default function CartDrawer({
  open, items, onClose, onUpdateQuantity, onRemoveItem, onOrderCreated,
}: {
  open: boolean; items: CartItem[];
  onClose: () => void;
  onUpdateQuantity: (pid: string, qty: number) => void;
  onRemoveItem: (pid: string) => void;
  onOrderCreated: (order: Order) => void;
}) {
  const { t, language } = useLanguage();
  const { message } = App.useApp();
  const total = items.reduce((s, i) => s + i.price * i.quantity, 0);

  async function handleCreateOrder() {
    if (!items.length) return;
    try {
      const order = await api.createOrderFromCart(items);
      message.success(t("chat.orderCreated", { orderId: order.order_id }));
      onOrderCreated(order);
    } catch (err) { message.error(err instanceof Error ? err.message : "Create order failed"); }
  }

  return (
    <Drawer title={<Space><ShoppingCartOutlined />{language === "zh" ? "购物车" : "Cart"}<Tag>{items.length} items</Tag></Space>} open={open} onClose={onClose} width={400}
      extra={<Button type="primary" icon={<CreditCardOutlined />} disabled={!items.length} onClick={handleCreateOrder}>{language === "zh" ? "创建订单" : "Create Order"}</Button>}>
      {items.length === 0 ? (
        <Typography.Text type="secondary">{language === "zh" ? "购物车为空" : "Cart is empty"}</Typography.Text>
      ) : (
        <>
          <List dataSource={items} renderItem={(item) => (
            <List.Item actions={[
              <InputNumber key="q" size="small" min={1} max={99} value={item.quantity} style={{ width: 60 }} onChange={(v) => v && onUpdateQuantity(item.product_id, v)} />,
              <Button key="d" type="text" danger size="small" icon={<DeleteOutlined />} onClick={() => onRemoveItem(item.product_id)} />,
            ]}>
              <List.Item.Meta title={item.name} description={<Space size={4} wrap><Tag>{item.category}</Tag>{currency(item.price)} × {item.quantity} = {currency(item.price * item.quantity)}</Space>} />
            </List.Item>
          )} />
          <div style={{ marginTop: 16, textAlign: "right" }}>
            <Typography.Text strong style={{ fontSize: 16 }}>Total: {currency(total)}</Typography.Text>
          </div>
        </>
      )}
    </Drawer>
  );
}
