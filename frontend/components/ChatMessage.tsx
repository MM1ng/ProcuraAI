"use client";

import { App, Button } from "antd";
import { CopyOutlined, RobotOutlined, UserOutlined } from "@ant-design/icons";
import { useLanguage } from "@/lib/i18n";

type ChatMessageProps = {
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
  createdAt?: string;
};

export default function ChatMessage({ role, content, streaming, createdAt: _createdAt }: ChatMessageProps) {
  const { t } = useLanguage();
  const { message } = App.useApp();

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(content);
      message.success(t("chat.copied"));
    } catch {
      message.error(t("chat.copyFailed"));
    }
  };

  return (
    <div className={`chat-row ${role === "user" ? "is-user" : "is-agent"}`}>
      <div className="chat-avatar">
        {role === "user" ? <UserOutlined /> : <RobotOutlined />}
      </div>
      <div className="chat-bubble">
        <div className="chat-header">
          <div className="chat-role">
            {role === "user" ? t("chat.requester") : t("chat.agent")}
          </div>
          <Button
            className="copy-btn"
            type="text"
            size="small"
            icon={<CopyOutlined />}
            onClick={handleCopy}
            aria-label={t("chat.copy")}
          />
        </div>
        <div className="chat-content">
          {content}
          {streaming ? <span className="stream-cursor" /> : null}
        </div>
      </div>
    </div>
  );
}
