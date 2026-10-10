"use client";

import { Button, Drawer, InputNumber, List, Space, Tag, Typography, App } from "antd";
import { CreditCardOutlined, DeleteOutlined, ShoppingCartOutlined } from "@ant-design/icons";
import { currency } from "@/lib/format";
import { useLanguage } from "@/lib/i18n";
import type { CartItem, Order } from "@/lib/types";
import { api } from "@/lib/api";
import { useState } from "react";

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
  const { message, modal } = App.useApp();
  const [confirming, setConfirming] = useState(false);
  const total = items.reduce((s, i) => s + i.price * i.quantity, 0);

  async function handleCreateOrder() {
    if (!items.length) return;
    setConfirming(true);
    try {
      const quote = await api.quoteCart(items);
      modal.confirm({
        title: language === "zh" ? "请确认当前购物车方案" : "Confirm the current cart plan",
        content: <Space direction="vertical" style={{ width: "100%" }}>
          {quote.plan.items.map((item, index) => <Typography.Text key={`${item.product_id}-${index}`}>
            {item.name} × {item.quantity}: {currency(item.subtotal)} ({item.delivery_days} {language === "zh" ? "天送达" : "days delivery"})
          </Typography.Text>)}
          <Typography.Text strong>{language === "zh" ? "总金额" : "Total"}: {currency(quote.plan.total_amount)}</Typography.Text>
        </Space>,
        okText: language === "zh" ? "确认并创建订单" : "Confirm and create order",
        cancelText: language === "zh" ? "取消" : "Cancel",
        onCancel: () => setConfirming(false),
        onOk: async () => {
          try {
            const order = await api.createOrderFromCart(quote.cart_token);
            message.success(t("chat.orderCreated", { orderId: order.order_id }));
            onOrderCreated(order);
          } catch (err) { message.error(err instanceof Error ? err.message : "Create order failed"); throw err; }
          finally { setConfirming(false); }
        },
      });
    } catch (err) { setConfirming(false); message.error(err instanceof Error ? err.message : "Create order failed"); }
  }

  return (
    <Drawer title={<Space><ShoppingCartOutlined />{language === "zh" ? "购物车" : "Cart"}<Tag>{items.length} items</Tag></Space>} open={open} onClose={onClose} width={400}
      extra={<Button type="primary" icon={<CreditCardOutlined />} disabled={!items.length || confirming} loading={confirming} onClick={handleCreateOrder}>{language === "zh" ? "创建订单" : "Create Order"}</Button>}>
      {items.length === 0 ? (
        <Typography.Text type="secondary">{language === "zh" ? "购物车为空" : "Cart is empty"}</Typography.Text>
      ) : (
        <>
          <Button onClick={async () => {
            try { await api.initializeCaller(); message.success("当前匿名会话已就绪。"); }
            catch (e) { message.error(e instanceof Error ? e.message : "匿名会话当前不可用。"); }
          }}>开始／恢复匿名购物车会话</Button>
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
