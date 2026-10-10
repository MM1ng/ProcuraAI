"use client";

import { Button, Result, Spin } from "antd";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import type { Order } from "@/lib/types";
import { useLanguage } from "@/lib/i18n";

export default function PaymentSuccessPage() {
  const { t } = useLanguage();
  const searchParams = useSearchParams();
  const orderId = searchParams.get("order_id");
  const sessionId = searchParams.get("session_id");
  const isMock = searchParams.get("mock") === "true";
  const [processing, setProcessing] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [order, setOrder] = useState<Order | null>(null);

  useEffect(() => {
    api.recoverPaymentReturn({ order_id: orderId || undefined, session_id: sessionId || undefined, mock: isMock })
      .then(saved => { setOrder(saved); setError(null); setProcessing(false); })
      .catch(e => { setProcessing(false); setError(e instanceof Error ? e.message : "当前无法核验支付结果。"); });
  }, [orderId, sessionId, isMock]);

  if (processing) {
    return (
      <Result
        status="info"
        title="正在核验支付结果"
        subTitle="Confirming payment..."
        extra={<Spin />}
      />
    );
  }

  return (
    <Result
      status={error ? "warning" : order?.status === "paid" ? "success" : "info"}
      title={error ? "当前无法核验支付结果" : order?.status === "paid" ? t("payment.successTitle") : "支付尚未确认"}
      subTitle={error || (order?.status === "paid" ? t("payment.successSubtitle") : "支付结果尚未确认，请稍后在订单页查看。")}
      extra={
        <>
        {!error && order?.status !== "paid" && order?.stripe_session_id?.startsWith("mock_") ? (
          <Button onClick={async () => {
            setProcessing(true);
            try {
              await api.mockPaymentSuccess(order.order_id, order.stripe_session_id!);
              setOrder(await api.recoverPaymentReturn({ order_id: order.order_id, session_id: order.stripe_session_id! }));
              setError(null);
            } catch (e) { setError(e instanceof Error ? e.message : "测试支付不可用"); }
            finally { setProcessing(false); }
          }}>测试：模拟本次支付完成</Button>
        ) : null}
        <Link href="/orders">
          <Button type="primary">{t("payment.orders")}</Button>
        </Link>
        </>
      }
    />
  );
}
