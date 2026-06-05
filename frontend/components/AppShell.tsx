"use client";

import {
  AppstoreOutlined,
  AuditOutlined,
  BarChartOutlined,
  GlobalOutlined,
  MessageOutlined,
  ProfileOutlined,
  ShoppingCartOutlined
} from "@ant-design/icons";
import { App as AntdApp, ConfigProvider, Layout, Menu, Select, Space, Typography } from "antd";
import type { ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import { LanguageProvider, languageOptions, useLanguage } from "@/lib/i18n";

const { Header, Sider, Content } = Layout;

export default function AppShell({ children }: { children: ReactNode }) {
  return (
    <LanguageProvider>
      <LocalizedAppShell>{children}</LocalizedAppShell>
    </LanguageProvider>
  );
}

function LocalizedAppShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { language, setLanguage, t } = useLanguage();
  const menuItems = [
    { key: "/chat", icon: <MessageOutlined />, label: t("nav.chat") },
    { key: "/products", icon: <AppstoreOutlined />, label: t("nav.products") },
    { key: "/procurement", icon: <ProfileOutlined />, label: t("nav.procurement") },
    { key: "/orders", icon: <ShoppingCartOutlined />, label: t("nav.orders") },
    { key: "/observability", icon: <BarChartOutlined />, label: t("nav.observability") },
    { key: "/evaluation", icon: <AuditOutlined />, label: t("nav.evaluation") }
  ];
  const selected = menuItems.find((item) => pathname.startsWith(item.key))?.key || "/chat";

  return (
    <ConfigProvider
      theme={{
        token: {
          borderRadius: 6,
          colorPrimary: "#2563eb",
          fontFamily:
            "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"
        },
        components: {
          Layout: { headerBg: "#ffffff", siderBg: "#101828" },
          Menu: { darkItemBg: "#101828", darkSubMenuItemBg: "#101828" }
        }
      }}
    >
      <AntdApp>
        <Layout style={{ minHeight: "100vh" }}>
          <Sider width={236} breakpoint="lg" collapsedWidth={0}>
            <div style={{ padding: 18, color: "#fff" }}>
              <Typography.Text style={{ color: "#fff", fontWeight: 700 }}>
                Enterprise Procurement Agent
              </Typography.Text>
            </div>
            <Menu
              theme="dark"
              mode="inline"
              selectedKeys={[selected]}
              items={menuItems}
              onClick={({ key }) => router.push(key)}
            />
          </Sider>
          <Layout>
            <Header
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "0 24px",
                borderBottom: "1px solid #e5e7eb"
              }}
            >
              <Typography.Title level={4} style={{ margin: 0 }}>
                Enterprise Procurement Agent
              </Typography.Title>
              <Space>
                <Typography.Text className="muted">{t("app.subtitle")}</Typography.Text>
                <Select
                  aria-label={t("language.label")}
                  value={language}
                  style={{ width: 132 }}
                  suffixIcon={<GlobalOutlined />}
                  options={languageOptions}
                  onChange={setLanguage}
                />
              </Space>
            </Header>
            <Content style={{ padding: 24 }}>{children}</Content>
          </Layout>
        </Layout>
      </AntdApp>
    </ConfigProvider>
  );
}
