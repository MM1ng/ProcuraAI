"use client";

import {
  AppstoreOutlined,
  AuditOutlined,
  BarChartOutlined,
  DashboardOutlined,
  GlobalOutlined,
  LoginOutlined,
  LogoutOutlined,
  MessageOutlined,
  ProfileOutlined,
  ShoppingCartOutlined,
  UserOutlined
} from "@ant-design/icons";
import { App as AntdApp, Button, ConfigProvider, Layout, Menu, Select, Space, Tag, Typography } from "antd";
import type { ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
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
  const { currentUser, isAuthenticated, isReady, logout } = useAuth();
  const { language, setLanguage, t } = useLanguage();

  const isLoginPage = pathname === "/login";

  // Build menu items based on role
  const baseMenuItems = [
    { key: "/chat", icon: <MessageOutlined />, label: t("nav.chat") },
    { key: "/products", icon: <AppstoreOutlined />, label: t("nav.products") },
    { key: "/procurement", icon: <ProfileOutlined />, label: t("nav.procurement") },
    { key: "/orders", icon: <ShoppingCartOutlined />, label: t("nav.orders") },
  ];

  const adminMenuItems = [
    { key: "/admin", icon: <DashboardOutlined />, label: t("nav.adminDashboard") },
    { key: "/observability", icon: <BarChartOutlined />, label: t("nav.observability") },
    { key: "/evaluation", icon: <AuditOutlined />, label: t("nav.evaluation") },
  ];

  const menuItems = currentUser?.role === "admin"
    ? [...baseMenuItems, ...adminMenuItems]
    : baseMenuItems;

  const selected = menuItems.find((item) => pathname.startsWith(item.key))?.key || "/chat";

  // Show nothing until auth is ready (prevents flash)
  if (!isReady) return null;

  // On login page, render children without layout chrome
  if (isLoginPage) {
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
        <AntdApp>{children}</AntdApp>
      </ConfigProvider>
    );
  }

  // If not authenticated and not on login page, show a minimal header with login button
  if (!isAuthenticated || !currentUser) {
    return (
      <ConfigProvider
        theme={{
          token: {
            borderRadius: 6,
            colorPrimary: "#2563eb",
            fontFamily:
              "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"
          }
        }}
      >
        <AntdApp>
          <Layout style={{ minHeight: "100vh" }}>
            <Header
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "0 24px",
                borderBottom: "1px solid #e5e7eb",
                background: "#fff"
              }}
            >
              <Typography.Title level={4} style={{ margin: 0 }}>
                E-commerce Assistant
              </Typography.Title>
              <Space>
                <Select
                  aria-label={t("language.label")}
                  value={language}
                  style={{ width: 132 }}
                  suffixIcon={<GlobalOutlined />}
                  options={languageOptions}
                  onChange={setLanguage}
                />
                <Button type="primary" icon={<LoginOutlined />} onClick={() => router.push("/login")}>
                  {t("auth.login")}
                </Button>
              </Space>
            </Header>
            <Content style={{ padding: 24 }}>{children}</Content>
          </Layout>
        </AntdApp>
      </ConfigProvider>
    );
  }

  const authenticatedUser = currentUser;

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
              <Typography.Text style={{ color: "#fff", fontWeight: 700, fontSize: 15 }}>
                E-commerce Assistant
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
                E-commerce Assistant
              </Typography.Title>
              <Space>
                <Tag color={authenticatedUser.role === "admin" ? "purple" : "blue"} icon={<UserOutlined />}>
                  {authenticatedUser.username} ({authenticatedUser.role === "admin" ? "Admin" : "User"})
                </Tag>
                <Select
                  aria-label={t("language.label")}
                  value={language}
                  style={{ width: 132 }}
                  suffixIcon={<GlobalOutlined />}
                  options={languageOptions}
                  onChange={setLanguage}
                />
                <Button
                  icon={<LogoutOutlined />}
                  onClick={() => {
                    logout();
                    router.push("/login");
                  }}
                >
                  {language === "zh" ? "退出登录" : "Logout"}
                </Button>
              </Space>
            </Header>
            <Content style={{ padding: 24 }}>{children}</Content>
          </Layout>
        </Layout>
      </AntdApp>
    </ConfigProvider>
  );
}
