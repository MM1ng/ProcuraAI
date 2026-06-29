"use client";

import { LockOutlined, ShoppingOutlined, UserOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Form, Input, Space, Tag, Typography } from "antd";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { useLanguage } from "@/lib/i18n";

type LoginForm = {
  username: string;
  password: string;
};

export default function LoginPage() {
  const router = useRouter();
  const { login } = useAuth();
  const { t } = useLanguage();
  const [error, setError] = useState("");

  function submit(values: LoginForm) {
    const user = login(values.username, values.password);
    if (!user) {
      setError(t("auth.invalidCredentials"));
      return;
    }
    router.replace(user.role === "admin" ? "/admin" : "/");
  }

  return (
    <main className="login-page">
      <Card className="login-card">
        <div className="login-brand">
          <div className="login-brand-mark">
            <ShoppingOutlined />
          </div>
          <div>
            <Typography.Title level={2} style={{ margin: 0 }}>
              {t("auth.loginTitle")}
            </Typography.Title>
            <Typography.Paragraph className="muted" style={{ marginBottom: 0 }}>
              {t("auth.loginSubtitle")}
            </Typography.Paragraph>
          </div>
        </div>
        {error ? <Alert type="error" showIcon message={error} style={{ marginBottom: 16 }} /> : null}
        <Form layout="vertical" onFinish={submit}>
          <Form.Item name="username" label={t("auth.username")} rules={[{ required: true }]}>
            <Input prefix={<UserOutlined />} autoComplete="username" />
          </Form.Item>
          <Form.Item name="password" label={t("auth.password")} rules={[{ required: true }]}>
            <Input.Password prefix={<LockOutlined />} autoComplete="current-password" />
          </Form.Item>
          <Button type="primary" htmlType="submit" block>
            {t("auth.login")}
          </Button>
        </Form>
        <div className="login-hints">
          <Typography.Text className="muted">{t("auth.demoAccounts")}</Typography.Text>
          <Space wrap>
            <Tag color="blue">user / user123</Tag>
            <Tag color="purple">admin / admin123</Tag>
          </Space>
        </div>
      </Card>
    </main>
  );
}
