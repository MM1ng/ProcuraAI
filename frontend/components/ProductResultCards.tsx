"use client";

import { Button, Card, Col, Row, Space, Tag, Typography } from "antd";
import { CreditCardOutlined, EyeOutlined, ShoppingCartOutlined } from "@ant-design/icons";
import { useState } from "react";
import { currency } from "@/lib/format";
import { useLanguage } from "@/lib/i18n";
import type { CartItem, Product } from "@/lib/types";
import ProductDetailModal from "./ProductDetailModal";

const DEFAULT_VISIBLE = 6;

export default function ProductResultCards({
  products, onAddToCart, onBuyNow,
}: { products: Product[]; onAddToCart: (i: CartItem) => void; onBuyNow: (p: Product) => void }) {
  const { translateCategory } = useLanguage();
  const [detail, setDetail] = useState<Product | null>(null);
  const [showAll, setShowAll] = useState(false);
  const visible = showAll ? products : products.slice(0, DEFAULT_VISIBLE);
  const hasMore = products.length > DEFAULT_VISIBLE;

  return (
    <div style={{ width: "100%", marginTop: 12 }}>
      <Row gutter={[12, 12]}>
        {visible.map((p) => {
          const inStock = (p.stock ?? 0) > 0;
          const fastDel = (p.delivery_days ?? 99) <= 5;
          const highRated = (p.rating ?? 0) >= 4.2;
          return (
            <Col xs={24} sm={12} lg={8} key={p.product_id}>
              <Card size="small" hoverable title={<Typography.Text ellipsis style={{ maxWidth: 200 }}>{p.name}</Typography.Text>}>
                <Space direction="vertical" size={6} style={{ width: "100%" }}>
                  <Space wrap size={[4, 4]}>
                    <Tag>{translateCategory(p.category)}</Tag>
                    <Tag color="blue">{p.brand}</Tag>
                    <Tag color={highRated ? "green" : "default"}>★ {(p.rating ?? 0).toFixed(1)}</Tag>
                  </Space>
                  <Space wrap size={[4, 4]}>
                    <Typography.Text strong style={{ fontSize: 16 }}>{currency(p.price)}</Typography.Text>
                    <Tag color={inStock ? "green" : "red"}>Stock: {p.stock ?? 0}</Tag>
                    <Tag color={fastDel ? "blue" : "orange"}>{p.delivery_days ?? "?"} days</Tag>
                  </Space>
                  <Typography.Text type="secondary" ellipsis>{p.supplier || "Unknown"}</Typography.Text>
                  <Row gutter={8}>
                    <Col span={8}><Button block size="small" icon={<EyeOutlined />} onClick={() => setDetail(p)}>Details</Button></Col>
                    <Col span={8}><Button block size="small" icon={<ShoppingCartOutlined />} disabled={!inStock} onClick={() => onAddToCart({ product_id: p.product_id, name: p.name, brand: p.brand, category: p.category, price: p.price, quantity: 1, supplier: p.supplier, delivery_days: p.delivery_days, stock: p.stock, rating: p.rating })}>Add to Cart</Button></Col>
                    <Col span={8}><Button block size="small" type="primary" icon={<CreditCardOutlined />} disabled={!inStock} onClick={() => onBuyNow(p)}>Buy Now</Button></Col>
                  </Row>
                </Space>
              </Card>
            </Col>
          );
        })}
      </Row>
      {hasMore || showAll ? (
        <div style={{ textAlign: "center", marginTop: 12 }}>
          {!showAll ? <Button type="link" onClick={() => setShowAll(true)}>Show More ({products.length - DEFAULT_VISIBLE} remaining)</Button>
          : <Button type="link" onClick={() => setShowAll(false)}>Show Less</Button>}
        </div>
      ) : null}
      <ProductDetailModal open={Boolean(detail)} item={detail} onClose={() => setDetail(null)} />
    </div>
  );
}
