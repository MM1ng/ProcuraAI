"use client";

import { Button, Result } from "antd";
import Link from "next/link";
import { useLanguage } from "@/lib/i18n";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function PaymentCancelPage() {
  const { t } = useLanguage();
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { api.callerContext().catch(e => setError(e instanceof Error ? e.message : "当前无法访问订单。")); }, []);

  return (
    <Result
      status="warning"
      title={error ? "当前无法访问订单" : t("payment.cancelTitle")}
      subTitle={error || t("payment.cancelSubtitle")}
      extra={
        <Link href="/orders">
          <Button type="primary">{t("payment.orders")}</Button>
        </Link>
      }
    />
  );
}
