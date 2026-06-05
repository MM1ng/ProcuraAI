import "@ant-design/v5-patch-for-react-19";
import "antd/dist/reset.css";
import "../styles/globals.css";
import type { Metadata } from "next";
import AppShell from "@/components/AppShell";

export const metadata: Metadata = {
  title: "Enterprise Procurement Agent",
  description: "Agentic RAG procurement assistant",
  icons: {
    icon: "/favicon.svg"
  }
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
