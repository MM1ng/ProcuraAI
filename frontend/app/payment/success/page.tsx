"use client";

import { Button, Result } from "antd";
import Link from "next/link";
import { useLanguage } from "@/lib/i18n";

export default function PaymentSuccessPage() {
  const { t } = useLanguage();

  return (
    <Result
      status="success"
      title={t("payment.successTitle")}
      subTitle={t("payment.successSubtitle")}
      extra={
        <Link href="/orders">
          <Button type="primary">{t("payment.orders")}</Button>
        </Link>
      }
    />
  );
}
