"use client";

import { Button, Result } from "antd";
import Link from "next/link";
import { useLanguage } from "@/lib/i18n";

export default function PaymentCancelPage() {
  const { t } = useLanguage();

  return (
    <Result
      status="warning"
      title={t("payment.cancelTitle")}
      subTitle={t("payment.cancelSubtitle")}
      extra={
        <Link href="/orders">
          <Button type="primary">{t("payment.orders")}</Button>
        </Link>
      }
    />
  );
}
