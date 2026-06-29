import "@ant-design/v5-patch-for-react-19";
import "antd/dist/reset.css";
import "../styles/globals.css";
import type { Metadata } from "next";
import AppShell from "@/components/AppShell";
import { AuthProvider } from "@/lib/auth";

export const metadata: Metadata = {
  title: "E-commerce Assistant",
  description: "Smart e-commerce assistant",
  icons: {
    icon: "/favicon.svg"
  }
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AuthProvider>
          <AppShell>{children}</AppShell>
        </AuthProvider>
      </body>
    </html>
  );
}
