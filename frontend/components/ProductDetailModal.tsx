"use client";

import { Descriptions, Modal, Tag } from "antd";
import { currency } from "@/lib/format";
import { useLanguage } from "@/lib/i18n";
import type { PlanItem, Product } from "@/lib/types";

type DetailSource = (Partial<Product> & Partial<PlanItem>) & {
  product_id?: string;
  name?: string;
  category?: string;
};

export default function ProductDetailModal({
  open, item, onClose,
}: { open: boolean; item: DetailSource | null; onClose: () => void }) {
  const { translateCategory } = useLanguage();
  if (!item) return null;

  const price = item.unit_price ?? item.price;
  return (
    <Modal title={item.name || "Product Detail"} open={open} onCancel={onClose} footer={null} width={560}>
      <Descriptions column={1} size="small" bordered>
        <Descriptions.Item label="Product ID">{item.product_id || "-"}</Descriptions.Item>
        <Descriptions.Item label="Name">{item.name || "-"}</Descriptions.Item>
        <Descriptions.Item label="Category">{translateCategory(item.category || "-")}</Descriptions.Item>
        <Descriptions.Item label="Brand">{item.brand || "-"}</Descriptions.Item>
        <Descriptions.Item label="Supplier">{item.supplier || "-"}</Descriptions.Item>
        <Descriptions.Item label="Price">{price !== undefined ? currency(Number(price)) : "-"}</Descriptions.Item>
        <Descriptions.Item label="Rating">
          {item.rating !== undefined && item.rating !== null ? (
            <Tag color={Number(item.rating) >= 4.2 ? "green" : Number(item.rating) >= 3.5 ? "orange" : "red"}>{item.rating}</Tag>
          ) : "-"}
        </Descriptions.Item>
        <Descriptions.Item label="Stock">
          {item.stock !== undefined && item.stock !== null ? (
            <Tag color={Number(item.stock) > 10 ? "green" : Number(item.stock) > 0 ? "orange" : "red"}>{item.stock}</Tag>
          ) : "-"}
        </Descriptions.Item>
        <Descriptions.Item label="Delivery Days">{item.delivery_days ?? "-"}</Descriptions.Item>
        {item.quantity !== undefined ? <Descriptions.Item label="Quantity">{item.quantity}</Descriptions.Item> : null}
        {(item as any).compliance_level ? <Descriptions.Item label="Compliance">{(item as any).compliance_level}</Descriptions.Item> : null}
        <Descriptions.Item label="Description">{item.description || "-"}</Descriptions.Item>
        {item.reason ? <Descriptions.Item label="Why Selected">{item.reason}</Descriptions.Item> : null}
      </Descriptions>
    </Modal>
  );
}
