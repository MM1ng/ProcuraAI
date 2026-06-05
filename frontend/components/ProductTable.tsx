"use client";

import { Alert, Button, Card, Input, InputNumber, Select, Space, Table, Tag } from "antd";
import type { ColumnsType } from "antd/es/table";
import { SearchOutlined, SyncOutlined } from "@ant-design/icons";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { currency } from "@/lib/format";
import { useLanguage } from "@/lib/i18n";
import type { Product } from "@/lib/types";

const categories = [
  "Laptop",
  "Monitor",
  "Keyboard",
  "Mouse",
  "Headset",
  "Webcam",
  "Office Chair",
  "Docking Station",
  "Printer",
  "Tablet",
  "Router",
  "External SSD",
  "Projector",
  "Conference Speaker",
  "Standing Desk"
];

export default function ProductTable() {
  const { t, translateCategory } = useLanguage();
  const [rows, setRows] = useState<Product[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState<Record<string, string | number | undefined>>({});

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const result = await api.products(filters);
      setRows(result.items);
    } catch {
      setRows([]);
      setError(t("products.loadFailed"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const columns: ColumnsType<Product> = [
    { title: t("products.product"), dataIndex: "name", key: "name", fixed: "left", width: 220 },
    {
      title: t("products.category"),
      dataIndex: "category",
      key: "category",
      width: 150,
      render: (value: string) => translateCategory(value)
    },
    { title: t("products.brand"), dataIndex: "brand", key: "brand", width: 120 },
    { title: t("products.price"), dataIndex: "price", key: "price", width: 110, render: currency },
    { title: t("products.rating"), dataIndex: "rating", key: "rating", width: 100 },
    { title: t("products.stock"), dataIndex: "stock", key: "stock", width: 90 },
    { title: t("products.delivery"), dataIndex: "delivery_days", key: "delivery_days", width: 100 },
    { title: t("products.supplier"), dataIndex: "supplier", key: "supplier", width: 190 },
    {
      title: t("products.compliance"),
      dataIndex: "compliance_level",
      key: "compliance_level",
      width: 130,
      render: (value: string) => <Tag>{value}</Tag>
    }
  ];

  return (
    <Card>
      <Space direction="vertical" size={12} style={{ width: "100%" }}>
        <div className="toolbar">
          <Input
            allowClear
            prefix={<SearchOutlined />}
            placeholder={t("products.search")}
            style={{ width: 240 }}
            onChange={(event) => setFilters((current) => ({ ...current, search: event.target.value }))}
          />
          <Select
            allowClear
            placeholder={t("products.category")}
            style={{ width: 190 }}
            options={categories.map((category) => ({ value: category, label: translateCategory(category) }))}
            onChange={(value) => setFilters((current) => ({ ...current, category: value }))}
          />
          <InputNumber
            placeholder={t("products.maxPrice")}
            min={0}
            onChange={(value) => setFilters((current) => ({ ...current, max_price: value ?? undefined }))}
          />
          <InputNumber
            placeholder={t("products.minRating")}
            min={0}
            max={5}
            step={0.1}
            onChange={(value) => setFilters((current) => ({ ...current, min_rating: value ?? undefined }))}
          />
          <InputNumber
            placeholder={t("products.minStock")}
            min={0}
            onChange={(value) => setFilters((current) => ({ ...current, min_stock: value ?? undefined }))}
          />
          <Button icon={<SyncOutlined />} onClick={load}>
            {t("products.apply")}
          </Button>
        </div>
        {error ? <Alert type="error" message={error} showIcon /> : null}
        <Table
          rowKey="product_id"
          loading={loading}
          columns={columns}
          dataSource={rows}
          scroll={{ x: 1320 }}
          pagination={{ pageSize: 12 }}
        />
      </Space>
    </Card>
  );
}
