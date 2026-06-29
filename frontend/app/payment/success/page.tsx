"use client";

import { Button, Result, Spin } from "antd";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { useLanguage } from "@/lib/i18n";

export default function PaymentSuccessPage() {
  const { t } = useLanguage();
  const searchParams = useSearchParams();
  const orderId = searchParams.get("order_id");
  const sessionId = searchParams.get("session_id");
  const isMock = searchParams.get("mock") === "true";
  const [processing, setProcessing] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (orderId && isMock) {
      // Mock payment: order_id is in the URL, call mock-success directly
      api
        .mockPaymentSuccess(orderId)
        .then(() => setProcessing(false))
        .catch((e) => {
          setProcessing(false);
          setError(e instanceof Error ? e.message : "Failed to confirm payment");
        });
    } else if (sessionId || orderId) {
      // Real Stripe payment: look up the order by session_id or order_id and mark paid.
      // The order_id fallback covers local/dev flows where no Stripe webhook reaches the backend.
      api
        .confirmPayment(sessionId ? { session_id: sessionId } : { order_id: orderId! })
        .then(() => setProcessing(false))
        .catch((e) => {
          setProcessing(false);
          setError(e instanceof Error ? e.message : "Failed to confirm payment");
        });
    } else {
      // No parameters — just show the success page
      setProcessing(false);
    }
  }, [orderId, sessionId, isMock]);

  if (processing) {
    return (
      <Result
        status="info"
        title={t("payment.successTitle")}
        subTitle="Confirming payment..."
        extra={<Spin />}
      />
    );
  }

  return (
    <Result
      status={error ? "warning" : "success"}
      title={t("payment.successTitle")}
      subTitle={error || t("payment.successSubtitle")}
      extra={
        <Link href="/orders">
          <Button type="primary">{t("payment.orders")}</Button>
        </Link>
      }
    />
  );
}
