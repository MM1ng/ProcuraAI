"use client";

import { Button, Card, Descriptions, Tag, Spin, Alert } from "antd";
import { ArrowLeftOutlined } from "@ant-design/icons";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { currency } from "@/lib/format";
import { useLanguage } from "@/lib/i18n";
import type { Product } from "@/lib/types";

export default function ProductDetailPage() {
  const params = useParams();
  const router = useRouter();
  const { t, translateCategory } = useLanguage();
  const [product, setProduct] = useState<Product | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const result = await api.getProduct(params.id as string);
        setProduct(result);
      } catch {
        setError(t("products.notFound"));
      } finally {
        setLoading(false);
      }
    }
    void load();
  }, [params.id]);

  if (loading) {
    return (
      <main className="page" style={{ display: "flex", justifyContent: "center", paddingTop: 80 }}>
        <Spin size="large" />
      </main>
    );
  }

  if (error || !product) {
    return (
      <main className="page">
        <div className="page-header">
          <Button icon={<ArrowLeftOutlined />} onClick={() => router.back()}>
            {t("products.back")}
          </Button>
        </div>
        <Alert type="error" message={error || t("products.notFound")} showIcon />
      </main>
    );
  }

  return (
    <main className="page">
      <div className="page-header">
        <Button icon={<ArrowLeftOutlined />} onClick={() => router.back()}>
          {t("products.back")}
        </Button>
      </div>
      <Card>
        <Descriptions
          title={product.name}
          bordered
          column={{ xs: 1, sm: 2, md: 3 }}
        >
          <Descriptions.Item label={t("products.product")}>{product.name}</Descriptions.Item>
          <Descriptions.Item label={t("products.category")}>
            {translateCategory(product.category)}
          </Descriptions.Item>
          <Descriptions.Item label={t("products.brand")}>{product.brand}</Descriptions.Item>
          <Descriptions.Item label={t("products.price")}>{currency(product.price)}</Descriptions.Item>
          <Descriptions.Item label={t("products.rating")}>{product.rating}</Descriptions.Item>
          <Descriptions.Item label={t("products.stock")}>{product.stock}</Descriptions.Item>
          <Descriptions.Item label={t("products.delivery")}>
            {product.delivery_days} {t("products.days")}
          </Descriptions.Item>
          <Descriptions.Item label={t("products.supplier")}>{product.supplier}</Descriptions.Item>
          <Descriptions.Item label={t("products.compliance")}>
            <Tag>{product.compliance_level}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label={t("products.description")} span={3}>
            {product.description || "-"}
          </Descriptions.Item>
        </Descriptions>
      </Card>
    </main>
  );
}
