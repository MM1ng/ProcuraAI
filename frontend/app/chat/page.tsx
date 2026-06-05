"use client";

import ChatPanel from "@/components/ChatPanel";
import { useLanguage } from "@/lib/i18n";

export default function ChatPage() {
  const { t } = useLanguage();

  return (
    <main className="page">
      <div className="page-header">
        <h1 className="page-title">{t("chat.title")}</h1>
      </div>
      <ChatPanel />
    </main>
  );
}
