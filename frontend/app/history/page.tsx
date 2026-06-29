"use client";

import { Button, Card, List, Popconfirm, Typography } from "antd";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useLanguage } from "@/lib/i18n";
import type { ProcurementHistoryRecord } from "@/lib/types";

export default function HistoryPage() {
  const { t } = useLanguage();
  const [records, setRecords] = useState<ProcurementHistoryRecord[]>([]);
  const [loading, setLoading] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const result = await api.history();
      setRecords(result.items);
    } finally {
      setLoading(false);
    }
  }

  async function remove(historyId: string) {
    await api.deleteHistory(historyId);
    setRecords((current) => current.filter((item) => item.id !== historyId));
  }

  useEffect(() => {
    void load();
  }, []);

  return (
    <main className="page">
      <div className="page-header">
        <h1 className="page-title">{t("nav.history")}</h1>
        <Button onClick={load} loading={loading}>{t("chat.refresh")}</Button>
      </div>
      <Card className="panel-card">
        <List
          loading={loading}
          dataSource={records}
          locale={{ emptyText: t("chat.noSavedHistory") }}
          renderItem={(item) => (
            <List.Item
              actions={[
                <Popconfirm key="delete" title={t("chat.deleteHistoryConfirm")} onConfirm={() => remove(item.id)}>
                  <Button danger type="text">{t("chat.delete")}</Button>
                </Popconfirm>
              ]}
            >
              <List.Item.Meta
                title={item.original_request || item.id}
                description={`${new Date(item.created_at).toLocaleString()} · $${item.total_cost.toFixed(2)}`}
              />
              <Typography.Text>{item.selected_plan?.items?.length || 0} {t("products.title")}</Typography.Text>
            </List.Item>
          )}
        />
      </Card>
    </main>
  );
}
